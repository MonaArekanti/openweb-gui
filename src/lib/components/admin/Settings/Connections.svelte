<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher, onMount, getContext, tick } from 'svelte';

	const dispatch = createEventDispatcher();

	import { getOllamaConfig, updateOllamaConfig, verifyOllamaConnection } from '$lib/apis/ollama';
	import {
		getOpenAIConfig,
		updateOpenAIConfig,
		getOpenAIModels,
		verifyOpenAIConnection
	} from '$lib/apis/openai';
	import { getModels as _getModels } from '$lib/apis';

	import { models, user } from '$lib/stores';

	import Switch from '$lib/components/common/Switch.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';

	import OpenAIConnection from './Connections/OpenAIConnection.svelte';
	import AddConnectionModal from './Connections/AddConnectionModal.svelte';
	import OllamaConnection from './Connections/OllamaConnection.svelte';

	const i18n = getContext('i18n');

	const getModels = async () => {
		const models = await _getModels(localStorage.token);
		return models;
	};

	// External
	let OLLAMA_BASE_URLS = [''];
	let OLLAMA_API_CONFIGS = {};

	let OPENAI_API_KEYS = [''];
	let OPENAI_API_BASE_URLS = [''];
	let OPENAI_API_CONFIGS = {};

	let ENABLE_OPENAI_API: null | boolean = null;
	let ENABLE_OLLAMA_API: null | boolean = null;

	let pipelineUrls = {};
	let showAddOpenAIConnectionModal = false;
	let showAddOllamaConnectionModal = false;

	let openaiReach: (boolean | null)[] = [];
	let ollamaReach: (boolean | null)[] = [];

	async function pingOpenAI() {
		if (!ENABLE_OPENAI_API) return;
		openaiReach = OPENAI_API_BASE_URLS.map(() => null);
		await Promise.all(
			OPENAI_API_BASE_URLS.map(async (u, i) => {
				try {
					await verifyOpenAIConnection(localStorage.token, u, OPENAI_API_KEYS[i] ?? '');
					openaiReach[i] = true;
				} catch {
					openaiReach[i] = false;
				}
			})
		);
		openaiReach = [...openaiReach];
	}

	async function pingOllama() {
		if (!ENABLE_OLLAMA_API) return;
		ollamaReach = OLLAMA_BASE_URLS.map(() => null);
		await Promise.all(
			OLLAMA_BASE_URLS.map(async (u, i) => {
				try {
					const cfg = OLLAMA_API_CONFIGS[u] || {};
					await verifyOllamaConnection(localStorage.token, u, cfg.key ?? '');
					ollamaReach[i] = true;
				} catch {
					ollamaReach[i] = false;
				}
			})
		);
		ollamaReach = [...ollamaReach];
	}

	const updateOpenAIHandler = async () => {
		if (ENABLE_OPENAI_API !== null) {
			OPENAI_API_BASE_URLS = OPENAI_API_BASE_URLS.filter(
				(url, urlIdx) => OPENAI_API_BASE_URLS.indexOf(url) === urlIdx && url !== ''
			).map((url) => url.replace(/\/$/, ''));

			// Check if API KEYS length is same than API URLS length
			if (OPENAI_API_KEYS.length !== OPENAI_API_BASE_URLS.length) {
				// if there are more keys than urls, remove the extra keys
				if (OPENAI_API_KEYS.length > OPENAI_API_BASE_URLS.length) {
					OPENAI_API_KEYS = OPENAI_API_KEYS.slice(0, OPENAI_API_BASE_URLS.length);
				}

				// if there are more urls than keys, add empty keys
				if (OPENAI_API_KEYS.length < OPENAI_API_BASE_URLS.length) {
					const diff = OPENAI_API_BASE_URLS.length - OPENAI_API_KEYS.length;
					for (let i = 0; i < diff; i++) {
						OPENAI_API_KEYS.push('');
					}
				}
			}

			const res = await updateOpenAIConfig(localStorage.token, {
				ENABLE_OPENAI_API: ENABLE_OPENAI_API,
				OPENAI_API_BASE_URLS: OPENAI_API_BASE_URLS,
				OPENAI_API_KEYS: OPENAI_API_KEYS,
				OPENAI_API_CONFIGS: OPENAI_API_CONFIGS
			}).catch((error) => {
				toast.error(error);
			});

			if (res) {
				toast.success($i18n.t('OpenAI API settings updated'));
				await models.set(await getModels());
				await pingOpenAI();
			}
		}
	};

	const updateOllamaHandler = async () => {
		if (ENABLE_OLLAMA_API !== null) {
			// Remove duplicate URLs
			OLLAMA_BASE_URLS = OLLAMA_BASE_URLS.filter(
				(url, urlIdx) => OLLAMA_BASE_URLS.indexOf(url) === urlIdx && url !== ''
			).map((url) => url.replace(/\/$/, ''));

			console.log(OLLAMA_BASE_URLS);

			if (OLLAMA_BASE_URLS.length === 0) {
				ENABLE_OLLAMA_API = false;
				toast.info($i18n.t('Ollama API disabled'));
			}

			const res = await updateOllamaConfig(localStorage.token, {
				ENABLE_OLLAMA_API: ENABLE_OLLAMA_API,
				OLLAMA_BASE_URLS: OLLAMA_BASE_URLS,
				OLLAMA_API_CONFIGS: OLLAMA_API_CONFIGS
			}).catch((error) => {
				toast.error(error);
			});

			if (res) {
				toast.success($i18n.t('Ollama API settings updated'));
				await models.set(await getModels());
				await pingOllama();
			}
		}
	};

	const addOpenAIConnectionHandler = async (connection) => {
		OPENAI_API_BASE_URLS = [...OPENAI_API_BASE_URLS, connection.url];
		OPENAI_API_KEYS = [...OPENAI_API_KEYS, connection.key];
		OPENAI_API_CONFIGS[connection.url] = connection.config;

		await updateOpenAIHandler();
	};

	const addOllamaConnectionHandler = async (connection) => {
		OLLAMA_BASE_URLS = [...OLLAMA_BASE_URLS, connection.url];
		OLLAMA_API_CONFIGS[connection.url] = connection.config;

		await updateOllamaHandler();
	};

	onMount(async () => {
		if ($user.role === 'admin') {
			let ollamaConfig = {};
			let openaiConfig = {};

			await Promise.all([
				(async () => {
					ollamaConfig = await getOllamaConfig(localStorage.token);
				})(),
				(async () => {
					openaiConfig = await getOpenAIConfig(localStorage.token);
				})()
			]);

			ENABLE_OPENAI_API = openaiConfig.ENABLE_OPENAI_API;
			ENABLE_OLLAMA_API = ollamaConfig.ENABLE_OLLAMA_API;

			OPENAI_API_BASE_URLS = openaiConfig.OPENAI_API_BASE_URLS;
			OPENAI_API_KEYS = openaiConfig.OPENAI_API_KEYS;
			OPENAI_API_CONFIGS = openaiConfig.OPENAI_API_CONFIGS;

			OLLAMA_BASE_URLS = ollamaConfig.OLLAMA_BASE_URLS;
			OLLAMA_API_CONFIGS = ollamaConfig.OLLAMA_API_CONFIGS;

			if (ENABLE_OPENAI_API) {
				for (const url of OPENAI_API_BASE_URLS) {
					if (!OPENAI_API_CONFIGS[url]) {
						OPENAI_API_CONFIGS[url] = {};
					}
				}

				OPENAI_API_BASE_URLS.forEach(async (url, idx) => {
					OPENAI_API_CONFIGS[url] = OPENAI_API_CONFIGS[url] || {};
					if (!(OPENAI_API_CONFIGS[url]?.enable ?? true)) {
						return;
					}
					const res = await getOpenAIModels(localStorage.token, idx);
					if (res.pipelines) {
						pipelineUrls[url] = true;
					}
				});
			}

			if (ENABLE_OLLAMA_API) {
				for (const url of OLLAMA_BASE_URLS) {
					if (!OLLAMA_API_CONFIGS[url]) {
						OLLAMA_API_CONFIGS[url] = {};
					}
				}
			}

			await pingOpenAI();
			await pingOllama();
		}
	});
</script>

<AddConnectionModal
	bind:show={showAddOpenAIConnectionModal}
	onSubmit={addOpenAIConnectionHandler}
/>

<AddConnectionModal
	ollama
	bind:show={showAddOllamaConnectionModal}
	onSubmit={addOllamaConnectionHandler}
/>

<form
	class="flex flex-col h-full justify-between text-sm"
	on:submit|preventDefault={() => {
		updateOpenAIHandler();
		updateOllamaHandler();

		dispatch('save');
	}}
>
	<div class=" overflow-y-scroll scrollbar-hidden h-full">
		{#if ENABLE_OPENAI_API !== null && ENABLE_OLLAMA_API !== null}
			<div class="my-2">
				<div class="mt-2 space-y-4 pr-1.5">
					<div class="flex justify-between items-center">
						<div class="text-base font-bold text-gray-900 dark:text-white">
							{$i18n.t('OpenAI API')}
						</div>

						{#if !ENABLE_OPENAI_API}
							<div class="flex items-center">
								<Switch
									bind:state={ENABLE_OPENAI_API}
									on:change={async () => {
										await updateOpenAIHandler();
									}}
								/>
							</div>
						{/if}
					</div>

					{#if ENABLE_OPENAI_API}
						<div>
							<div class="w-[60vw] max-w-full">
								<div
									class="rounded-lg border border-[#e0e0e0] bg-white dark:border-gray-600 dark:bg-gray-900 overflow-hidden"
								>
									<div
										class="flex items-center justify-between gap-3 border-b border-[#e0e0e0] bg-white px-4 py-2.5 dark:border-gray-700 dark:bg-gray-900"
									>
										<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
											{$i18n.t('Manage OpenAI API Connections')}
										</div>
										<div class="flex shrink-0 items-center gap-2">
											<Switch
												bind:state={ENABLE_OPENAI_API}
												on:change={async () => {
													await updateOpenAIHandler();
												}}
											/>
											<Tooltip content={$i18n.t(`Add Connection`)}>
												<button
													class="p-1 text-xl leading-none text-gray-400 hover:text-gray-700 dark:text-gray-500 dark:hover:text-gray-200 transition rounded-md"
													on:click={() => {
														showAddOpenAIConnectionModal = true;
													}}
													type="button"
													aria-label={$i18n.t('Add Connection')}
												>
													<Plus />
												</button>
											</Tooltip>
										</div>
									</div>
									<table class="w-full table-fixed border-collapse text-sm">
										<colgroup>
											<col />
											<col style="width: 112px" />
											<col style="width: 148px" />
											<col style="width: 184px" />
										</colgroup>
										<thead>
											<tr class="border-b border-[#e0e0e0] bg-white dark:border-gray-700 dark:bg-gray-900">
												<th
													class="align-middle px-4 py-3 text-left text-[13px] font-bold text-gray-900 dark:text-white"
													scope="col">{$i18n.t('Connection URL')}</th
												>
												<th
													class="align-middle px-4 py-3 text-left text-[13px] font-bold text-gray-900 dark:text-white"
													scope="col">{$i18n.t('Provider')}</th
												>
												<th
													class="align-middle px-4 py-3 text-left text-[13px] font-bold text-gray-900 dark:text-white"
													scope="col">{$i18n.t('Status')}</th
												>
												<th
													class="align-middle px-4 py-3 text-right text-[13px] font-bold text-gray-900 dark:text-white"
													scope="col">{$i18n.t('Actions')}</th
												>
											</tr>
										</thead>
									<tbody>
										{#each OPENAI_API_BASE_URLS as url, idx}
											<OpenAIConnection
												pipeline={pipelineUrls[url] ? true : false}
												bind:url
												bind:key={OPENAI_API_KEYS[idx]}
												bind:config={OPENAI_API_CONFIGS[url]}
												reachable={openaiReach[idx] ?? null}
												onSubmit={() => {
													updateOpenAIHandler();
												}}
												onDelete={() => {
													OPENAI_API_BASE_URLS = OPENAI_API_BASE_URLS.filter(
														(url, urlIdx) => idx !== urlIdx
													);
													OPENAI_API_KEYS = OPENAI_API_KEYS.filter(
														(key, keyIdx) => idx !== keyIdx
													);
												}}
											/>
										{/each}
										</tbody>
									</table>
								</div>
							</div>
						</div>
					{/if}
				</div>
			</div>

			<hr class=" border-gray-50 dark:border-gray-850" />

			<div class="pr-1.5 my-2">
				<div class="flex justify-between items-center mb-4">
					<div class="text-base font-bold text-gray-900 dark:text-white">
						{$i18n.t('Ollama API')}
					</div>

					{#if !ENABLE_OLLAMA_API}
						<Switch
							bind:state={ENABLE_OLLAMA_API}
							on:change={async () => {
								await updateOllamaHandler();
							}}
						/>
					{/if}
				</div>

				{#if ENABLE_OLLAMA_API}
					<div>
						<div class="w-[60vw] max-w-full">
							<div
								class="rounded-lg border border-[#e0e0e0] bg-white dark:border-gray-600 dark:bg-gray-900 overflow-hidden"
							>
								<div
									class="flex items-center justify-between gap-3 border-b border-[#e0e0e0] bg-white px-4 py-2.5 dark:border-gray-700 dark:bg-gray-900"
								>
									<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
										{$i18n.t('Manage Ollama API Connections')}
									</div>
									<div class="flex shrink-0 items-center gap-2">
										<Switch
											bind:state={ENABLE_OLLAMA_API}
											on:change={async () => {
												await updateOllamaHandler();
											}}
										/>
										<Tooltip content={$i18n.t(`Add Connection`)}>
											<button
												class="p-1 text-xl leading-none text-gray-400 hover:text-gray-700 dark:text-gray-500 dark:hover:text-gray-200 transition rounded-md"
												on:click={() => {
													showAddOllamaConnectionModal = true;
												}}
												type="button"
												aria-label={$i18n.t('Add Connection')}
											>
												<Plus />
											</button>
										</Tooltip>
									</div>
								</div>
								<table class="w-full table-fixed border-collapse text-sm">
									<colgroup>
										<col />
										<col style="width: 148px" />
										<col style="width: 184px" />
									</colgroup>
									<thead>
										<tr class="border-b border-[#e0e0e0] bg-white dark:border-gray-700 dark:bg-gray-900">
											<th
												class="align-middle px-4 py-3 text-left text-[13px] font-bold text-gray-900 dark:text-white"
												scope="col">{$i18n.t('Connection URL')}</th
											>
											<th
												class="align-middle px-4 py-3 text-left text-[13px] font-bold text-gray-900 dark:text-white"
												scope="col">{$i18n.t('Status')}</th
											>
											<th
												class="align-middle px-4 py-3 text-right text-[13px] font-bold text-gray-900 dark:text-white"
												scope="col">{$i18n.t('Actions')}</th
											>
										</tr>
									</thead>
								<tbody>
									{#each OLLAMA_BASE_URLS as url, idx}
										<OllamaConnection
											bind:url
											bind:config={OLLAMA_API_CONFIGS[url]}
											reachable={ollamaReach[idx] ?? null}
											onMigrateUrl={(from, to) => {
												const cfg = OLLAMA_API_CONFIGS[from];
												if (cfg !== undefined) {
													OLLAMA_API_CONFIGS[to] = cfg;
													delete OLLAMA_API_CONFIGS[from];
													OLLAMA_API_CONFIGS = { ...OLLAMA_API_CONFIGS };
												}
											}}
											onSubmit={() => {
												updateOllamaHandler();
											}}
											onDelete={() => {
												OLLAMA_BASE_URLS = OLLAMA_BASE_URLS.filter(
													(url, urlIdx) => idx !== urlIdx
												);
											}}
										/>
									{/each}
									</tbody>
								</table>
							</div>
						</div>

						<div class="mt-3 text-xs text-gray-500 dark:text-gray-400">
							{$i18n.t('Trouble accessing Ollama?')}
							<a
								class="font-medium text-[#2EC4B6] underline hover:text-[#26b0a5]"
								href="https://github.com/open-webui/open-webui#troubleshooting"
								target="_blank"
								rel="noopener noreferrer"
							>
								{$i18n.t('Click here for help.')}
							</a>
						</div>
					</div>
				{/if}
			</div>
		{:else}
			<div class="flex h-full justify-center">
				<div class="my-auto">
					<Spinner className="size-6" />
				</div>
			</div>
		{/if}
	</div>

	<div class="flex justify-end pt-3 text-sm font-medium">
		<button
			class="px-3.5 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full"
			type="submit"
		>
			{$i18n.t('Save')}
		</button>
	</div>
</form>
