/** Keep real focus; only the keyboard locator follows the most recent input. */
export function trackInputModality(): () => void {
  const root = document.documentElement;
  const update = (mode: 'pointer' | 'keyboard'): void => {
    if (root.dataset.input !== mode) { root.dataset.input = mode; document.dispatchEvent(new Event('input-modality-change')); }
  };
  const pointer = (): void => update('pointer');
  const keyboard = (event: KeyboardEvent): void => {
    if (!event.altKey && !event.ctrlKey && !event.metaKey && ['Tab','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home','End','PageUp','PageDown','Enter',' ','Escape'].includes(event.key)) update('keyboard');
  };
  update('pointer');
  document.addEventListener('pointerdown', pointer, true);
  document.addEventListener('keydown', keyboard, true);
  return () => { document.removeEventListener('pointerdown', pointer, true); document.removeEventListener('keydown', keyboard, true); };
}
