import { request } from "./api";
import type { LoginResponse } from "../types/api";

export function loginWithWechatCode(code: string): Promise<LoginResponse> {
  return request<LoginResponse, { code: string }>("/miniapp/auth/login", {
    method: "POST",
    data: { code },
  });
}
