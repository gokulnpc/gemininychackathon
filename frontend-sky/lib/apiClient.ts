import axios from "axios";
import { auth } from "@/lib/firebase";

const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
});

// Request interceptor — attach Firebase ID token to every request
apiClient.interceptors.request.use(async (config) => {
  const token = await auth.currentUser?.getIdToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor — redirect to login on 401 (with loop guard)
let redirecting = false;
apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (
      err.response?.status === 401 &&
      typeof window !== "undefined" &&
      !redirecting &&
      !window.location.pathname.startsWith("/login")
    ) {
      redirecting = true;
      // Clear stale cookie before redirect to break any loop
      document.cookie = "firebase_token=; path=/; max-age=0";
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default apiClient;
