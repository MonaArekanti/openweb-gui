import { WEBUI_API_BASE_URL } from '$lib/constants';
import { getWebUIClientSessionId } from '$lib/utils/clientSession';

export type UploadApiErrorBody = {
	detail?:
		| string
		| {
				code?: string;
				message?: string;
				detection_type?: string;
		  };
};

/** Backend blocked upload due to sensitivity validation (no file stored). */
export function isUploadSensitiveBlockedError(err: unknown): boolean {
	const code = parseUploadErrorCode(err);
	return (
		code === 'upload_sensitive_blocked' ||
		code === 'upload_metadata_sensitive' ||
		code === 'upload_content_sensitive'
	);
}

export function parseUploadErrorCode(err: unknown): string | null {
	if (!err || typeof err !== 'object' || !('detail' in err)) return null;
	const d = (err as UploadApiErrorBody).detail;
	if (d && typeof d === 'object' && d !== null && 'code' in d && typeof (d as { code?: string }).code === 'string') {
		return (d as { code: string }).code;
	}
	return null;
}

/** Maps backend upload validation errors to user-facing strings. */
export function getUploadErrorMessage(
	err: unknown,
	t: (key: string, opts?: Record<string, unknown>) => string
): string {
	if (err && typeof err === 'object' && 'detail' in err) {
		const d = (err as UploadApiErrorBody).detail;
		if (d && typeof d === 'object' && d !== null && 'code' in d) {
			const code = (d as { code?: string }).code;
			if (code === 'upload_sensitive_blocked') {
				return t('Sensitive content detected. This document cannot be uploaded.');
			}
			if (code === 'upload_metadata_sensitive') {
				return t('Sensitive file detected. Upload blocked.');
			}
			if (code === 'upload_content_sensitive') {
				return t('Sensitive content detected inside the document.');
			}
			const message = (d as { message?: string }).message;
			if (typeof message === 'string' && message.length > 0) {
				return message;
			}
		}
		if (typeof d === 'string') {
			return d;
		}
	}
	if (err instanceof Error && err.message) {
		return err.message;
	}
	return t('Failed to upload file.');
}

export const uploadFile = async (token: string, file: File) => {
	const data = new FormData();
	data.append('file', file);

	const sid = getWebUIClientSessionId();
	const res = await fetch(`${WEBUI_API_BASE_URL}/files/`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			authorization: `Bearer ${token}`,
			...(sid ? { 'X-WebUI-Client-Session': sid } : {})
		},
		body: data
	});

	let body: unknown = {};
	try {
		body = await res.json();
	} catch {
		body = {};
	}

	if (!res.ok) {
		throw body;
	}

	return body;
};

export const uploadDir = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/upload/dir`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getFiles = async (token: string = '') => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getFileById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/${id}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateFileDataContentById = async (token: string, id: string, content: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/${id}/data/content/update`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			content: content
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getFileContentById = async (id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/${id}/content`, {
		method: 'GET',
		headers: {
			Accept: 'application/json'
		},
		credentials: 'include'
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return await res.blob();
		})
		.catch((err) => {
			error = err.detail;
			console.log(err);

			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteFileById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/${id}`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteAllFiles = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/all`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
