/** Keep real focus; only the keyboard locator follows the most recent input. */
export function trackInputModality(): () => void {
  const root = document.documentElement;
  const update = (mode: 'pointer' | 'keyboard'): void => { if (root.dataset.input !== mode) root.dataset.input = mode; };
  const pointer = (): void => update('pointer');
  const keyboard = (event: KeyboardEvent): void => { if (!['Shift', 'Control', 'Alt', 'Meta'].includes(event.key)) update('keyboard'); };
  update('pointer');
  document.addEventListener('pointerdown', pointer, true);
  document.addEventListener('keydown', keyboard, true);
  return () => { document.removeEventListener('pointerdown', pointer, true); document.removeEventListener('keydown', keyboard, true); };
}
