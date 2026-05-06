import { WEBUI_API_BASE_URL } from '$lib/constants';

export type TokensSummary = {
	total_tokens: number;
	total_estimated_cost_usd: number;
	avg_tokens_per_message: number;
	rate_per_token_usd: number;
};

export type TokensDaily = {
	today_tokens: number;
	today_cost_usd: number;
	yesterday_tokens: number;
	yesterday_cost_usd: number;
	change_percent: number | null;
};

export type ModelBarRow = {
	model_id: string;
	model_name: string;
	value: number;
};

export type BreakdownRow = {
	model_id: string;
	model_name: string;
	total_tokens: number;
	price_per_1k_usd: number;
	total_cost_usd: number;
};

export type TokenBreakdownResponse = {
	rows: BreakdownRow[];
};

async function adminTokensFetch<T>(token: string, path: string): Promise<T> {
	const res = await fetch(`${WEBUI_API_BASE_URL}/admin/tokens${path}`, {
		headers: {
			Accept: 'application/json',
			Authorization: `Bearer ${token}`
		}
	});
	if (!res.ok) throw await res.json();
	return res.json();
}

export async function getTokensSummary(token: string): Promise<TokensSummary> {
	return adminTokensFetch<TokensSummary>(token, '/summary');
}

export async function getTokensDaily(token: string): Promise<TokensDaily> {
	return adminTokensFetch<TokensDaily>(token, '/daily');
}

export async function getModelTokenBars(
	token: string,
	params: { start_date: string; end_date: string; metric: 'tokens' | 'price' }
): Promise<ModelBarRow[]> {
	const q = new URLSearchParams({
		start_date: params.start_date,
		end_date: params.end_date,
		metric: params.metric
	});
	return adminTokensFetch<ModelBarRow[]>(token, `/model-bars?${q}`);
}

export async function getTokenBreakdown(
	token: string,
	userId?: string
): Promise<TokenBreakdownResponse> {
	const q = userId ? `?user_id=${encodeURIComponent(userId)}` : '';
	return adminTokensFetch<TokenBreakdownResponse>(token, `/breakdown${q}`);
}
