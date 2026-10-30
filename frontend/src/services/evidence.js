// Selection never falls back to another response's citations.
export function selectedEvidenceMessage(messages, selectedId) {
  return selectedId === null ? messages.at(-1) : messages.find(message => message.id === selectedId);
}
