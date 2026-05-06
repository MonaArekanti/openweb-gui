import { WEBUI_API_BASE_URL } from '$lib/constants';

export type AdminChatUser = {
	id: string;
	name: string;
	email: string;
};

export type AdminChatRow = {
	id: string;
	title: string;
	titles_display: string;
	user: AdminChatUser;
	model: string;
	model_name: string;
	message_count: number;
	created_at: number;
	updated_at: number;
	tags: string[];
};

export type AdminChatStats = {
	total_documents: number;
	flagged_documents: number;
};

export type AdminMessageRow = {
	role: string;
	content: string;
	timestamp?: number | null;
	model?: string | null;
	model_name?: string | null;
	name?: string | null;
};

async function adminFetch<T>(
	token: string,
	path: string,
	opts?: RequestInit
): Promise<T> {
	const res = await fetch(`${WEBUI_API_BASE_URL}/admin/chats${path}`, {
		...opts,
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`,
			...(opts?.headers || {})
		}
	});
	if (!res.ok) throw await res.json();
	return res.json();
}

export async function getAdminChatStats(
	token: string,
	params?: {
		user_id?: string;
		model_id?: string;
		tag?: string;
		start_date?: string;
		end_date?: string;
	}
): Promise<AdminChatStats> {
	const sp = new URLSearchParams();
	if (params?.user_id) sp.set('user_id', params.user_id);
	if (params?.model_id) sp.set('model_id', params.model_id);
	if (params?.tag) sp.set('tag', params.tag);
	if (params?.start_date) sp.set('start_date', params.start_date);
	if (params?.end_date) sp.set('end_date', params.end_date);
	const q = sp.toString();
	return adminFetch<AdminChatStats>(token, q ? `/stats?${q}` : '/stats');
}

export async function getAdminChats(
	token: string,
	params: {
		user_id?: string;
		model_id?: string;
		tag?: string;
		start_date?: string;
		end_date?: string;
		page?: number;
		limit?: number;
	}
): Promise<AdminChatRow[]> {
	const sp = new URLSearchParams();
	if (params.user_id) sp.set('user_id', params.user_id);
	if (params.model_id) sp.set('model_id', params.model_id);
	if (params.tag) sp.set('tag', params.tag);
	if (params.start_date) sp.set('start_date', params.start_date);
	if (params.end_date) sp.set('end_date', params.end_date);
	sp.set('page', String(params.page ?? 1));
	sp.set('limit', String(params.limit ?? 20));
	const q = sp.toString();
	return adminFetch<AdminChatRow[]>(token, `/?${q}`);
}

export async function getAdminChatMessages(
	token: string,
	chatId: string
): Promise<AdminMessageRow[]> {
	return adminFetch<AdminMessageRow[]>(token, `/${encodeURIComponent(chatId)}/messages`);
}
