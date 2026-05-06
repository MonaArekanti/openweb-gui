<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { v4 as uuidv4 } from 'uuid';

	import { goto } from '$app/navigation';
	import {
		user,
		chats,
		chatId,
		tags,
		showSidebar,
		mobile,
		showArchivedChats,
		pinnedChats,
		scrollPaginationEnabled,
		currentChatPage,
		temporaryChatEnabled,
		channels,
		socket,
		config,
		WEBUI_NAME
	} from '$lib/stores';
	import { onMount, getContext, tick, onDestroy } from 'svelte';

	const i18n = getContext('i18n');

	import {
		deleteChatById,
		getChatList,
		getAllTags,
		createNewChat,
		getPinnedChatList,
		toggleChatPinnedStatusById,
		getChatPinnedStatusById,
		getChatById,
		updateChatFolderIdById,
		importChat
	} from '$lib/apis/chats';
	import { createNewFolder, getFolders, updateFolderParentIdById } from '$lib/apis/folders';
	import ArchivedChatsModal from './Sidebar/ArchivedChatsModal.svelte';
	import UserMenu from './Sidebar/UserMenu.svelte';
	import ChatItem from './Sidebar/ChatItem.svelte';
	import Spinner from '../common/Spinner.svelte';
	import Loader from '../common/Loader.svelte';
	import AddFilesPlaceholder from '../AddFilesPlaceholder.svelte';
	import SearchInput from './Sidebar/SearchInput.svelte';
	import Folder from '../common/Folder.svelte';
	import Plus from '../icons/Plus.svelte';
	import Tooltip from '../common/Tooltip.svelte';
	import Folders from './Sidebar/Folders.svelte';
	import { getChannels, createNewChannel } from '$lib/apis/channels';
	import ChannelModal from './Sidebar/ChannelModal.svelte';
	import ChannelItem from './Sidebar/ChannelItem.svelte';
	import PencilSquare from '../icons/PencilSquare.svelte';
	import { createEmptyChatAndNavigate } from '$lib/utils/chat/createEmptyChat';

	const BREAKPOINT = 768;

	let navElement;
	let search = '';

	let shiftKey = false;

	let foldersSectionOpen = true;
	let chatsSectionOpen = true;

	$: folderPickList = Object.keys(folders)
		.filter((id) => folders[id]?.name)
		.map((id) => ({ id, name: folders[id].name }))
		.sort((a, b) => a.name.localeCompare(b.name));

	const userInitials = (name: string) => {
		if (!name?.trim()) return '?';
		return name
			.trim()
			.split(/\s+/)
			.filter(Boolean)
			.slice(0, 2)
			.map((p) => p[0])
			.join('')
			.toUpperCase()
			.slice(0, 2);
	};

	const handleChatFolderDrop = async (e) => {
		const { type, id, item } = e.detail;

		if (type === 'chat') {
			let chat = await getChatById(localStorage.token, id).catch((error) => {
				return null;
			});
			if (!chat && item) {
				chat = await importChat(localStorage.token, item.chat, item?.meta ?? {});
			}

			if (chat) {
				if (chat.folder_id) {
					await updateChatFolderIdById(localStorage.token, chat.id, null).catch((error) => {
						toast.error(error);
						return null;
					});
				}

				if (chat.pinned) {
					await toggleChatPinnedStatusById(localStorage.token, chat.id);
				}

				initChatList();
			}
		} else if (type === 'folder') {
			if (!folders[id] || folders[id].parent_id === null) {
				return;
			}

			const res = await updateFolderParentIdById(localStorage.token, id, null).catch((error) => {
				toast.error(error);
				return null;
			});

			if (res) {
				await initFolders();
			}
		}
	};

	let selectedChatId = null;
	let showPinnedChat = true;

	let showCreateChannel = false;

	// Pagination variables
	let chatListLoading = false;
	let allChatsLoaded = false;

	let folders = {};

	const initFolders = async () => {
		const folderList = await getFolders(localStorage.token).catch((error) => {
			toast.error(error);
			return [];
		});

		folders = {};

		// First pass: Initialize all folder entries
		for (const folder of folderList) {
			// Ensure folder is added to folders with its data
			folders[folder.id] = { ...(folders[folder.id] || {}), ...folder };
		}

		// Second pass: Tie child folders to their parents
		for (const folder of folderList) {
			if (folder.parent_id) {
				// Ensure the parent folder is initialized if it doesn't exist
				if (!folders[folder.parent_id]) {
					folders[folder.parent_id] = {}; // Create a placeholder if not already present
				}

				// Initialize childrenIds array if it doesn't exist and add the current folder id
				folders[folder.parent_id].childrenIds = folders[folder.parent_id].childrenIds
					? [...folders[folder.parent_id].childrenIds, folder.id]
					: [folder.id];

				// Sort the children by updated_at field
				folders[folder.parent_id].childrenIds.sort((a, b) => {
					return folders[b].updated_at - folders[a].updated_at;
				});
			}
		}
	};

	const promptNewFolder = () => {
		const entered = window.prompt($i18n.t('Enter folder name'), '');
		if (entered === null) {
			return;
		}
		const name = entered.trim();
		createFolder(name === '' ? 'Untitled' : name);
	};

	const createFolder = async (name = 'Untitled') => {
		if (name === '') {
			toast.error($i18n.t('Folder name cannot be empty.'));
			return;
		}

		const rootFolders = Object.values(folders).filter((folder) => folder.parent_id === null);
		if (rootFolders.find((folder) => folder.name.toLowerCase() === name.toLowerCase())) {
			// If a folder with the same name already exists, append a number to the name
			let i = 1;
			while (
				rootFolders.find((folder) => folder.name.toLowerCase() === `${name} ${i}`.toLowerCase())
			) {
				i++;
			}

			name = `${name} ${i}`;
		}

		// Add a dummy folder to the list to show the user that the folder is being created
		const tempId = uuidv4();
		folders = {
			...folders,
			tempId: {
				id: tempId,
				name: name,
				created_at: Date.now(),
				updated_at: Date.now()
			}
		};

		const res = await createNewFolder(localStorage.token, name).catch((error) => {
			toast.error(error);
			return null;
		});

		if (res) {
			await initFolders();
		}
	};

	const initChannels = async () => {
		await channels.set(await getChannels(localStorage.token));
	};

	const initChatList = async () => {
		// Reset pagination variables
		try {
			tags.set(await getAllTags(localStorage.token));
			pinnedChats.set(await getPinnedChatList(localStorage.token));
			await initFolders();

			currentChatPage.set(1);
			allChatsLoaded = false;

			await chats.set(await getChatList(localStorage.token, $currentChatPage));

			// Enable pagination
			scrollPaginationEnabled.set(true);
		} catch (error) {
			console.error(error);
			toast.error(`${error}`);
			await chats.set([]);
			scrollPaginationEnabled.set(true);
		}
	};

	const loadMoreChats = async () => {
		chatListLoading = true;

		currentChatPage.set($currentChatPage + 1);

		let newChatList = [];

		try {
			newChatList = await getChatList(localStorage.token, $currentChatPage);

			// once the bottom of the list has been reached (no results) there is no need to continue querying
			allChatsLoaded = newChatList.length === 0;
			await chats.set([...($chats ? $chats : []), ...newChatList]);
		} catch (error) {
			console.error(error);
			toast.error(`${error}`);
			allChatsLoaded = true;
		}

		chatListLoading = false;
	};

	/** Title-only client filter (instant); flat list newest-first */
	$: normalizedSearch = search.trim().toLowerCase();
	$: chatsForDisplay = [...($chats ?? [])]
		.filter(
			(c) => !normalizedSearch || (c.title ?? '').toLowerCase().includes(normalizedSearch)
		)
		.sort((a, b) => (b.updated_at ?? 0) - (a.updated_at ?? 0));

	$: if (typeof window !== 'undefined') {
		localStorage.sidebarFoldersOpen = String(foldersSectionOpen);
		localStorage.sidebarChatsOpen = String(chatsSectionOpen);
	}

	const onSearchClear = () => {
		search = '';
	};

	const importChatHandler = async (items, pinned = false, folderId = null) => {
		console.log('importChatHandler', items, pinned, folderId);
		for (const item of items) {
			console.log(item);
			if (item.chat) {
				await importChat(localStorage.token, item.chat, item?.meta ?? {}, pinned, folderId);
			}
		}

		initChatList();
	};

	const inputFilesHandler = async (files) => {
		console.log(files);

		for (const file of files) {
			const reader = new FileReader();
			reader.onload = async (e) => {
				const content = e.target.result;

				try {
					const chatItems = JSON.parse(content);
					importChatHandler(chatItems);
				} catch {
					toast.error($i18n.t(`Invalid file format.`));
				}
			};

			reader.readAsText(file);
		}
	};

	const tagEventHandler = async (type, tagName, chatId) => {
		console.log(type, tagName, chatId);
		if (type === 'delete') {
			initChatList();
		} else if (type === 'add') {
			initChatList();
		}
	};

	let draggedOver = false;

	const onDragOver = (e) => {
		e.preventDefault();

		// Check if a file is being draggedOver.
		if (e.dataTransfer?.types?.includes('Files')) {
			draggedOver = true;
		} else {
			draggedOver = false;
		}
	};

	const onDragLeave = () => {
		draggedOver = false;
	};

	const onDrop = async (e) => {
		e.preventDefault();
		console.log(e); // Log the drop event

		// Perform file drop check and handle it accordingly
		if (e.dataTransfer?.files) {
			const inputFiles = Array.from(e.dataTransfer?.files);

			if (inputFiles && inputFiles.length > 0) {
				console.log(inputFiles); // Log the dropped files
				inputFilesHandler(inputFiles); // Handle the dropped files
			}
		}

		draggedOver = false; // Reset draggedOver status after drop
	};

	let touchstart;
	let touchend;

	function checkDirection() {
		const screenWidth = window.innerWidth;
		const swipeDistance = Math.abs(touchend.screenX - touchstart.screenX);
		if (touchstart.clientX < 40 && swipeDistance >= screenWidth / 8) {
			if (touchend.screenX < touchstart.screenX) {
				showSidebar.set(false);
			}
			if (touchend.screenX > touchstart.screenX) {
				showSidebar.set(true);
			}
		}
	}

	const onTouchStart = (e) => {
		touchstart = e.changedTouches[0];
		console.log(touchstart.clientX);
	};

	const onTouchEnd = (e) => {
		touchend = e.changedTouches[0];
		checkDirection();
	};

	const onKeyDown = (e) => {
		if (e.key === 'Shift') {
			shiftKey = true;
		}
	};

	const onKeyUp = (e) => {
		if (e.key === 'Shift') {
			shiftKey = false;
		}
	};

	const onFocus = () => {};

	const onBlur = () => {
		shiftKey = false;
		selectedChatId = null;
	};

	onMount(async () => {
		showPinnedChat = localStorage?.showPinnedChat ? localStorage.showPinnedChat === 'true' : true;
		foldersSectionOpen = localStorage.sidebarFoldersOpen !== 'false';
		chatsSectionOpen = localStorage.sidebarChatsOpen !== 'false';

		mobile.subscribe((e) => {
			if ($showSidebar && e) {
				showSidebar.set(false);
			}

			if (!$showSidebar && !e) {
				showSidebar.set(true);
			}
		});

		showSidebar.set(!$mobile ? localStorage.sidebar === 'true' : false);
		showSidebar.subscribe((value) => {
			localStorage.sidebar = value;
		});

		await initChannels();
		await initChatList();

		window.addEventListener('keydown', onKeyDown);
		window.addEventListener('keyup', onKeyUp);

		window.addEventListener('touchstart', onTouchStart);
		window.addEventListener('touchend', onTouchEnd);

		window.addEventListener('focus', onFocus);
		window.addEventListener('blur', onBlur);

		const dropZone = document.getElementById('sidebar');

		dropZone?.addEventListener('dragover', onDragOver);
		dropZone?.addEventListener('drop', onDrop);
		dropZone?.addEventListener('dragleave', onDragLeave);
	});

	onDestroy(() => {
		window.removeEventListener('keydown', onKeyDown);
		window.removeEventListener('keyup', onKeyUp);

		window.removeEventListener('touchstart', onTouchStart);
		window.removeEventListener('touchend', onTouchEnd);

		window.removeEventListener('focus', onFocus);
		window.removeEventListener('blur', onBlur);

		const dropZone = document.getElementById('sidebar');

		dropZone?.removeEventListener('dragover', onDragOver);
		dropZone?.removeEventListener('drop', onDrop);
		dropZone?.removeEventListener('dragleave', onDragLeave);
	});
</script>

<ArchivedChatsModal
	bind:show={$showArchivedChats}
	on:change={async () => {
		await initChatList();
	}}
/>

<ChannelModal
	bind:show={showCreateChannel}
	onSubmit={async ({ name, access_control }) => {
		const res = await createNewChannel(localStorage.token, {
			name: name,
			access_control: access_control
		}).catch((error) => {
			toast.error(error);
			return null;
		});

		if (res) {
			$socket.emit('join-channels', { auth: { token: $user.token } });
			await initChannels();
			showCreateChannel = false;
		}
	}}
/>

<!-- svelte-ignore a11y-no-static-element-interactions -->

{#if $showSidebar}
	<div
		class=" fixed md:hidden z-40 top-0 right-0 left-0 bottom-0 bg-black/60 w-full min-h-screen h-screen flex justify-center overflow-hidden overscroll-contain"
		on:mousedown={() => {
			showSidebar.set(!$showSidebar);
		}}
	/>
{/if}

<div
	bind:this={navElement}
	id="sidebar"
	class="h-screen max-h-[100dvh] min-h-screen select-none {$showSidebar
		? 'md:relative w-[260px] max-w-[260px]'
		: '-translate-x-[260px] w-[0px]'} bg-[#f5f5f5] dark:bg-gray-950 text-gray-900 dark:text-gray-200 text-[14px] transition-[transform,width] duration-300 ease-out fixed z-50 top-0 left-0 overflow-hidden border-r border-gray-200/70 dark:border-gray-800 font-primary
        "
	data-state={$showSidebar}
>
	<div
		class="flex flex-col h-full min-h-0 w-[260px] z-50 {$showSidebar ? '' : 'invisible'}"
	>
		<header class="flex shrink-0 items-center gap-2 px-4 py-4">
			<span class="font-bold text-lg leading-none text-black dark:text-white tracking-tight">O|</span>
			<span
				class="flex-1 text-center font-bold text-[15px] text-black dark:text-white truncate px-1"
			>
				{$WEBUI_NAME}
			</span>
			<button
				type="button"
				class="shrink-0 p-1.5 rounded-lg hover:bg-black/[0.06] dark:hover:bg-white/10 text-gray-900 dark:text-gray-100 transition"
				aria-label={$i18n.t('Toggle sidebar')}
				on:click={() => showSidebar.set(!$showSidebar)}
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					fill="none"
					viewBox="0 0 24 24"
					stroke-width="1.5"
					stroke="currentColor"
					class="w-[22px] h-[22px]"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M3.75 6A2.25 2.25 0 0 1 6 3.75h3.75A2.25 2.25 0 0 1 12 6v12a2.25 2.25 0 0 1-2.25 2.25H6A2.25 2.25 0 0 1 3.75 18V6ZM12 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 22.25 6v12a2.25 2.25 0 0 1-2.25 2.25h-3.75A2.25 2.25 0 0 1 12 18V6Z"
					/>
				</svg>
			</button>
		</header>

		<a
			id="sidebar-new-chat-button"
			class="mx-3 mb-1 flex items-center gap-3 rounded-xl px-4 py-2.5 text-left hover:bg-[#efefef] dark:hover:bg-gray-900 transition shrink-0"
			href="/"
			draggable="false"
			on:click|preventDefault={async () => {
				selectedChatId = null;
				chatId.set('');
				if ($temporaryChatEnabled) {
					await goto('/');
					const newChatButton = document.getElementById('new-chat-button');
					setTimeout(() => {
						newChatButton?.click();
						if ($mobile) {
							showSidebar.set(false);
						}
					}, 0);
					return;
				}
				try {
					await createEmptyChatAndNavigate($i18n.t('New Chat'));
					if ($mobile) {
						showSidebar.set(false);
					}
				} catch (error) {
					console.error(error);
					toast.error(`${error}`);
				}
			}}
		>
			<PencilSquare className="size-[18px] shrink-0 text-gray-800 dark:text-gray-200" strokeWidth="2" />
			<span class="font-medium text-[14px] text-gray-900 dark:text-white">
				{$i18n.t('New Chat')}
			</span>
		</a>

		<div class="relative shrink-0 px-4 pb-3 {$temporaryChatEnabled ? 'opacity-40 pointer-events-none' : ''}">
			{#if $temporaryChatEnabled}
				<div class="absolute inset-0 z-10 cursor-not-allowed" aria-hidden="true"></div>
			{/if}
			<SearchInput
				variant="sidebar"
				showTagSuggestions={false}
				bind:value={search}
				on:clear={onSearchClear}
				placeholder={$i18n.t('Search')}
			/>
		</div>

		<div class="flex flex-col gap-0.5 px-3 pb-2 text-gray-800 dark:text-gray-200 shrink-0">
			<a
				class="flex items-center gap-3 rounded-xl px-4 py-2.5 hover:bg-[#efefef] dark:hover:bg-gray-900 transition"
				href="/notes"
				on:click={() => {
					selectedChatId = null;
					chatId.set('');
					if ($mobile) {
						showSidebar.set(false);
					}
				}}
				draggable="false"
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					fill="none"
					viewBox="0 0 24 24"
					stroke-width="1.5"
					stroke="currentColor"
					class="size-[18px] shrink-0 text-gray-800 dark:text-gray-200"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5a1.125 1.125 0 0 1-1.125-1.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z"
					/>
				</svg>
				<span class="font-medium text-[14px]">{$i18n.t('Notes')}</span>
			</a>

			<a
				class="flex items-center gap-3 rounded-xl px-4 py-2.5 hover:bg-[#efefef] dark:hover:bg-gray-900 transition"
				href="/workspace"
				on:click={() => {
					selectedChatId = null;
					chatId.set('');
					if ($mobile) {
						showSidebar.set(false);
					}
				}}
				draggable="false"
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					fill="none"
					viewBox="0 0 24 24"
					stroke-width="1.5"
					stroke="currentColor"
					class="size-[18px] shrink-0 text-gray-800 dark:text-gray-200"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM3.75 15.75A2.25 2.25 0 0 1 6 13.5h2.25a2.25 2.25 0 0 1 2.25 2.25V18a2.25 2.25 0 0 1-2.25 2.25H6A2.25 2.25 0 0 1 3.75 18v-2.25ZM13.5 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 22.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H15.75a2.25 2.25 0 0 1-2.25-2.25V6Zm3.75 9.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18a2.25 2.25 0 0 1-2.25 2.25h-2.25A2.25 2.25 0 0 1 15 18v-2.25Z"
					/>
				</svg>
				<span class="font-medium text-[14px]">{$i18n.t('Workspace')}</span>
			</a>
		</div>

		<div
			class="relative flex flex-col flex-1 min-h-0 overflow-hidden {$temporaryChatEnabled ? 'opacity-40' : ''}"
		>
			{#if $config?.features?.enable_channels && ($user.role === 'admin' || $channels.length > 0) && !normalizedSearch}
				<Folder
					className="px-2 mt-0.5"
					name={$i18n.t('Channels')}
					dragAndDrop={false}
					onAdd={$user.role === 'admin'
						? () => {
								showCreateChannel = true;
							}
						: null}
					onAddLabel={$i18n.t('Create Channel')}
				>
					{#each $channels as channel}
						<ChannelItem
							{channel}
							onUpdate={async () => {
								await initChannels();
							}}
						/>
					{/each}
				</Folder>
			{/if}

			{#if !normalizedSearch}
				<Folder
					bind:open={foldersSectionOpen}
					collapsible={true}
					className="px-1 mt-0.5"
					name={$i18n.t('Folders')}
					onAdd={() => {
						promptNewFolder();
					}}
					onAddLabel={$i18n.t('New Folder')}
					on:import={(e) => {
						importChatHandler(e.detail);
					}}
					on:drop={handleChatFolderDrop}
				>
					{#if $temporaryChatEnabled}
						<div class="absolute z-40 w-full h-full flex justify-center"></div>
					{/if}

					<Folders
						{folders}
						on:import={(e) => {
							const { folderId, items } = e.detail;
							importChatHandler(items, false, folderId);
						}}
						on:update={async (e) => {
							initChatList();
						}}
						on:change={async () => {
							initChatList();
						}}
					/>
				</Folder>
			{/if}

			<Folder
				bind:open={chatsSectionOpen}
				collapsible={true}
				className="px-1 mt-0.5 flex flex-col flex-1 min-h-0"
				name={$i18n.t('Chats')}
				on:import={(e) => {
					importChatHandler(e.detail);
				}}
				on:drop={handleChatFolderDrop}
			>
				{#if $temporaryChatEnabled}
					<div class="absolute z-40 w-full h-full flex justify-center"></div>
				{/if}

				<div class="flex flex-col flex-1 min-h-0">
				{#if !normalizedSearch && $pinnedChats.length > 0}
					<div class="flex flex-col space-y-1 rounded-xl shrink-0">
						<Folder
							className=""
							bind:open={showPinnedChat}
							on:change={(e) => {
								localStorage.setItem('showPinnedChat', e.detail);
								console.log(e.detail);
							}}
							on:import={(e) => {
								importChatHandler(e.detail, true);
							}}
							on:drop={async (e) => {
								const { type, id, item } = e.detail;

								if (type === 'chat') {
									let chat = await getChatById(localStorage.token, id).catch((error) => {
										return null;
									});
									if (!chat && item) {
										chat = await importChat(localStorage.token, item.chat, item?.meta ?? {});
									}

									if (chat) {
										console.log(chat);
										if (chat.folder_id) {
											const res = await updateChatFolderIdById(
												localStorage.token,
												chat.id,
												null
											).catch((error) => {
												toast.error(error);
												return null;
											});
										}

										if (!chat.pinned) {
											const res = await toggleChatPinnedStatusById(localStorage.token, chat.id);
										}

										initChatList();
									}
								}
							}}
							name={$i18n.t('Pinned')}
						>
							<div
								class="ml-3 pl-1 mt-[1px] flex flex-col overflow-y-auto scrollbar-hidden border-s border-gray-100 dark:border-gray-900"
							>
								{#each $pinnedChats as chat}
									<ChatItem
										className=""
										id={chat.id}
										title={chat.title}
										folderOptions={folderPickList}
										{shiftKey}
										selected={selectedChatId === chat.id}
										on:select={() => {
											selectedChatId = chat.id;
										}}
										on:unselect={() => {
											selectedChatId = null;
										}}
										on:change={async () => {
											initChatList();
										}}
										on:tag={(e) => {
											const { type, name } = e.detail;
											tagEventHandler(type, name, chat.id);
										}}
									/>
								{/each}
							</div>
						</Folder>
					</div>
				{/if}

				<div
					class="flex-1 min-h-0 flex flex-col overflow-y-auto overflow-x-hidden scrollbar-hidden scroll-smooth px-1"
				>
					<div class="pt-1 pb-4">
						{#if $chats}
							{#if !normalizedSearch && $chats.length === 0}
								<div
									class="py-10 px-3 text-center text-[13px] text-[#999] dark:text-gray-500 leading-relaxed"
								>
									{$i18n.t('No chats yet')}
								</div>
							{:else if normalizedSearch && chatsForDisplay.length === 0}
								<div
									class="py-10 px-3 text-center text-[13px] text-[#999] dark:text-gray-500 leading-relaxed"
								>
									{$i18n.t('No results found')}
								</div>
							{/if}
							{#each chatsForDisplay as chat}
								<ChatItem
									className=""
									id={chat.id}
									title={chat.title}
									folderOptions={folderPickList}
									{shiftKey}
									selected={selectedChatId === chat.id}
									on:select={() => {
										selectedChatId = chat.id;
									}}
									on:unselect={() => {
										selectedChatId = null;
									}}
									on:change={async () => {
										initChatList();
									}}
									on:tag={(e) => {
										const { type, name } = e.detail;
										tagEventHandler(type, name, chat.id);
									}}
								/>
							{/each}

							{#if $scrollPaginationEnabled && !allChatsLoaded}
								<Loader
									on:visible={(e) => {
										if (!chatListLoading) {
											loadMoreChats();
										}
									}}
								>
									<div
										class="w-full flex justify-center py-1 text-xs animate-pulse items-center gap-2"
									>
										<Spinner className=" size-4" />
										<div class=" ">Loading...</div>
									</div>
								</Loader>
							{/if}
						{:else}
							<div class="space-y-2 px-2 pt-2" aria-busy="true">
								{#each [1, 2, 3, 4, 5, 6] as _}
									<div
										class="h-10 rounded-xl bg-gray-200/90 dark:bg-gray-800/90 animate-pulse"
									></div>
								{/each}
							</div>
							{/if}
					</div>
				</div>
				</div>
			</Folder>
		</div>

		<div
			class="shrink-0 border-t border-gray-200/80 dark:border-gray-800 px-4 py-3 mt-auto bg-[#f5f5f5] dark:bg-gray-950"
		>
			<div class="flex flex-col font-primary">
				{#if $user !== undefined}
					<UserMenu
						role={$user.role}
						on:show={(e) => {
							if (e.detail === 'archived-chat') {
								showArchivedChats.set(true);
							}
						}}
					>
						<button
							type="button"
							class="flex items-center gap-3 rounded-xl py-2 px-1 w-full hover:bg-[#efefef] dark:hover:bg-gray-900 transition text-left"
						>
							<div class="relative shrink-0">
								<div
									class="flex items-center justify-center w-9 h-9 rounded-full bg-orange-500 text-white text-xs font-bold shadow-sm"
								>
									{userInitials($user.name)}
								</div>
								<span
									class="absolute bottom-0 right-0 block h-2.5 w-2.5 rounded-full bg-green-500 ring-2 ring-[#f5f5f5] dark:ring-gray-950"
									aria-hidden="true"
								></span>
							</div>
							<div class="min-w-0 flex-1 font-semibold text-[14px] text-gray-900 dark:text-white truncate">
								{$user.name}
							</div>
						</button>
					</UserMenu>
				{/if}
			</div>
		</div>
	</div>
</div>

<style>
	.scrollbar-hidden:active::-webkit-scrollbar-thumb,
	.scrollbar-hidden:focus::-webkit-scrollbar-thumb,
	.scrollbar-hidden:hover::-webkit-scrollbar-thumb {
		visibility: visible;
	}
	.scrollbar-hidden::-webkit-scrollbar-thumb {
		visibility: hidden;
	}
</style>
