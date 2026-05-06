import { WEBUI_API_BASE_URL } from '$lib/constants';

export type AnalyticsSummary = {
	messages: number;
	tokens: number;
	chats: number;
	users: number;
	estimated_cost: number;
};

export type UsageOverTimeRow = {
	date: string;
	model: string;
	count: number;
};

export type ModelUsageRow = {
	model_id?: string | null;
	model: string;
	messages: number;
	tokens: number;
	share_percent: number;
};

export type UserActivityRow = {
	rank: number;
	user: string;
	role: string;
	messages: number;
	tokens: number;
};

export type HeatmapDayRow = {
	date: string;
	messages: number;
	tokens: number;
};

async function adminFetch<T>(token: string, path: string): Promise<T> {
	const res = await fetch(`${WEBUI_API_BASE_URL}/admin/analytics${path}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	});
	if (!res.ok) {
		throw await res.json().catch(() => ({ detail: res.statusText }));
	}
	return res.json();
}

export async function getAnalyticsSummary(token: string): Promise<AnalyticsSummary> {
	return adminFetch(token, '/summary');
}

export async function getUsageOverTime(
	token: string,
	params: {
		metric: 'messages' | 'tokens';
		start_date: string;
		end_date: string;
		user_id?: string;
		model_id?: string;
	}
): Promise<UsageOverTimeRow[]> {
	const sp = new URLSearchParams({
		metric: params.metric,
		start_date: params.start_date,
		end_date: params.end_date
	});
	if (params.user_id) sp.set('user_id', params.user_id);
	if (params.model_id) sp.set('model_id', params.model_id);
	return adminFetch(token, `/usage-over-time?${sp.toString()}`);
}

export async function getModelUsage(token: string): Promise<ModelUsageRow[]> {
	return adminFetch(token, '/model-usage');
}

export async function getUserActivity(token: string): Promise<UserActivityRow[]> {
	return adminFetch(token, '/user-activity');
}

export async function getUserActivityHeatmap(
	token: string,
	year: number
): Promise<HeatmapDayRow[]> {
	const sp = new URLSearchParams({ year: String(year) });
	return adminFetch(token, `/user-activity-heatmap?${sp.toString()}`);
}
