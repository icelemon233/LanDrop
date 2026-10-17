from __future__ import annotations

import re
import secrets
import time

from .errors import AppError


class SessionManager:
    def __init__(self, lock):
        self.lock = lock
        self.sessions: dict[str, dict] = {}
        self.pair_token = secrets.token_urlsafe(24)
        self.admin_token = secrets.token_urlsafe(32)
        self.desktop_tickets: dict[str, float] = {}

    def issue_desktop_url(self, port: int) -> str:
        with self.lock:
            now = time.monotonic()
            self.desktop_tickets = {key: expires for key, expires in self.desktop_tickets.items() if expires > now}
            if len(self.desktop_tickets) >= 32:
                self.desktop_tickets.pop(next(iter(self.desktop_tickets)))
            ticket = secrets.token_urlsafe(24)
            self.desktop_tickets[ticket] = now + 300
            return f'http://127.0.0.1:{port}/desktop/{ticket}'

    def consume_ticket(self, ticket: str) -> bool:
        with self.lock:
            return self.desktop_tickets.pop(ticket, 0) > time.monotonic()

    def create(self, role: str, user_agent: str, peer: str) -> str:
        with self.lock:
            now = time.time()
            self.sessions = {key: value for key, value in self.sessions.items() if now - value['created'] < 86400}
            if role == 'admin':
                admins = sorted(((key, value['created']) for key, value in self.sessions.items() if value['role'] == 'admin'), key=lambda item: item[1])
                for key, _ in admins[:-7]:
                    self.sessions.pop(key, None)
            elif sum(value['role'] == 'phone' for value in self.sessions.values()) >= 32:
                raise AppError('手机连接数量已达上限，请在电脑上断开不用的设备。', 429, 'session-limit')
            token = secrets.token_urlsafe(32)
            platform = '安卓手机' if 'Android' in user_agent else 'iPhone / iPad' if re.search(r'iPhone|iPad', user_agent) else '浏览器设备'
            self.sessions[token] = {'role': role, 'id': secrets.token_hex(8), 'name': platform, 'created': now, 'seen': now, 'peer': peer}
            return token

    def get(self, token: str) -> dict | None:
        with self.lock:
            session = self.sessions.get(token)
            if session and time.time() - session['created'] < 86400:
                session['seen'] = time.time()
                return session.copy()
            self.sessions.pop(token, None)
            return None

    def reset_phones(self):
        with self.lock:
            self.pair_token = secrets.token_urlsafe(24)
            self.sessions = {key: value for key, value in self.sessions.items() if value['role'] == 'admin'}

    def revoke(self, identifier: str):
        with self.lock:
            self.sessions = {key: value for key, value in self.sessions.items() if value['id'] != identifier or value['role'] == 'admin'}

    def devices(self) -> list[dict]:
        with self.lock:
            return [{key: value for key, value in session.items() if key not in {'role', 'created'}} for session in self.sessions.values() if session['role'] == 'phone' and time.time() - session['created'] < 86400]
