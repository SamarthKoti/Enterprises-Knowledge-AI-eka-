export async function api(path, options = {}) {
  const multipart = options.body instanceof FormData;
  const response = await fetch(`/api${path}`, {
    credentials: 'include', ...options,
    headers: {...(!multipart && options.body ? {'Content-Type': 'application/json'} : {}), ...options.headers},
  });
  const body = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('eka:unauthorized'));
    const detail = typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map(item => item.msg).join('; ') : body.results?.find(item => item.error)?.error?.detail;
    const error = new Error(detail || 'Request failed. Please try again.');
    error.status = response.status;
    throw error;
  }
  return body;
}
