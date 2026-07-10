const API = import.meta.env.VITE_API_URL ?? "";

// apiFetch : ajoute le Bearer access token et rejoue après refresh sur 401 (Chap 7).
export async function apiFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const token = localStorage.getItem("access_token");
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response = await fetch(`${API}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  if (response.status === 401 && token) {
    const refreshed = await fetch(`${API}/api/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (refreshed.ok) {
      const data = (await refreshed.json()) as { access_token: string };
      localStorage.setItem("access_token", data.access_token);
      headers.set("Authorization", `Bearer ${data.access_token}`);
      response = await fetch(`${API}${path}`, {
        ...options,
        headers,
        credentials: "include",
      });
    }
  }
  return response;
}
