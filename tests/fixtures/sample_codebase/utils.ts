// Plain utility file with no AI imports
export function formatDate(date: Date): string {
  return date.toISOString().split('T')[0];
}

export function slugify(text: string): string {
  return text.toLowerCase().replace(/\s+/g, '-');
}
