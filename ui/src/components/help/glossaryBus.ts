/** Event kecil agar komponen mana pun bisa membuka GlossaryDrawer tanpa prop drilling. */

export const OPEN_GLOSSARY_EVENT = 'saham:open-glossary';

export interface OpenGlossaryDetail {
  /** Key istilah yang langsung disorot (opsional). */
  term?: string;
}

export function openGlossary(term?: string) {
  window.dispatchEvent(new CustomEvent<OpenGlossaryDetail>(OPEN_GLOSSARY_EVENT, { detail: { term } }));
}
