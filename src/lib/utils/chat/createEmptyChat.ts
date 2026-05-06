import { v4 as uuidv4 } from 'uuid';
import { get } from 'svelte/store';

import { goto } from '$app/navigation';

import { createNewChat, getChatList } from '$lib/apis/chats';
import { chats, config, currentChatPage, models, settings } from '$lib/stores';

function resolveDefaultModels(): string[] {
	const $models = get(models);
	let selectedModels: string[] = [];

	if (typeof sessionStorage !== 'undefined' && sessionStorage.selectedModels) {
		try {
			selectedModels = JSON.parse(sessionStorage.selectedModels);
		} catch {
			/* ignore */
		}
	}

	if (selectedModels.length === 0) {
		const $settings = get(settings);
		const $config = get(config);
		if ($settings?.models) {
			selectedModels = $settings.models;
		} else if ($config?.default_models) {
			selectedModels = $config.default_models.split(',');
		}
	}

	selectedModels = selectedModels.filter((modelId) => $models.map((m) => m.id).includes(modelId));
	if (selectedModels.length === 0 || (selectedModels.length === 1 && selectedModels[0] === '')) {
		if ($models.length > 0) {
			selectedModels = [$models[0].id];
		} else {
			selectedModels = [''];
		}
	}

	return selectedModels;
}

/**
 * Persists a new empty chat on the server and navigates to it (sidebar "New Chat").
 */
export async function createEmptyChatAndNavigate(newChatTitle: string) {
	const token = localStorage.token;
	const emptyHistory = { messages: {}, currentId: null };
	const selectedModels = resolveDefaultModels();
	const $settings = get(settings);

	const chat = await createNewChat(token, {
		id: uuidv4(),
		title: newChatTitle,
		models: selectedModels,
		system: $settings?.system ?? undefined,
		params: {},
		history: emptyHistory,
		messages: [],
		tags: [],
		timestamp: Date.now()
	});

	currentChatPage.set(1);
	try {
		await chats.set(await getChatList(token, 1));
	} catch (e) {
		console.error(e);
	}
	await goto(`/c/${chat.id}`);
	return chat;
}
