function makeTokenStore(key: string) {
  return {
    get: (): string | null => localStorage.getItem(key),
    set: (token: string): void => localStorage.setItem(key, token),
    clear: (): void => localStorage.removeItem(key),
    isLoggedIn: (): boolean => !!localStorage.getItem(key),
  };
}

export const userToken = makeTokenStore("nanobot_manager_token");
export const adminToken = makeTokenStore("nanobot_manager_admin_token");

// Keep named exports for backward compatibility
export const getToken = userToken.get;
export const setToken = userToken.set;
export const clearToken = userToken.clear;
export const isLoggedIn = userToken.isLoggedIn;

export const getAdminToken = adminToken.get;
export const setAdminToken = adminToken.set;
export const clearAdminToken = adminToken.clear;
export const isAdminLoggedIn = adminToken.isLoggedIn;
