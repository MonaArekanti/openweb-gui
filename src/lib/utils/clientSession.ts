/** Stable anonymous session id for analytics (upload rejection correlation); not auth. */
export function getWebUIClientSessionId(): string {
	if (typeof window === 'undefined' || typeof localStorage === 'undefined') {
		return '';
	}
	let id = localStorage.getItem('webui_client_session');
	if (!id) {
		id =
			typeof crypto !== 'undefined' && crypto.randomUUID
				? crypto.randomUUID()
				: `ws-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
		localStorage.setItem('webui_client_session', id);
	}
	return id;
}
