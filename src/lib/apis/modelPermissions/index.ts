import { WEBUI_API_BASE_URL } from '$lib/constants';

export type ModelPermissionRow = {
	model_id: string;
	provider: string;
	model_name: string;
	users_enabled: boolean;
	groups_enabled: boolean;
};

async function adminFetch<T>(token: string, path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(`${WEBUI_API_BASE_URL}/admin/permissions${path}`, {
		...init,
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`,
			...(init?.headers || {})
		}
	});
	if (!res.ok) throw await res.json().catch(() => ({ detail: res.statusText }));
	return res.json();
}

export async function getModelPermissions(token: string): Promise<ModelPermissionRow[]> {
	return adminFetch<ModelPermissionRow[]>(token, '/');
}

export async function patchModelPermission(
	token: string,
	modelId: string,
	body: { users_enabled?: boolean; groups_enabled?: boolean }
): Promise<ModelPermissionRow> {
	const enc = encodeURIComponent(modelId);
	return adminFetch<ModelPermissionRow>(token, `/${enc}`, {
		method: 'PATCH',
		body: JSON.stringify(body)
	});
}
