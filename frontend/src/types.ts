export type UserRole = "admin" | "manager";
export type IncidentType = "sleep" | "absence" | "phone" | "smoking" | "anomalous_movement";

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
}

export interface UserMe {
  id: number;
  username: string;
  role: UserRole;
}

export interface Camera {
  id: number;
  name: string;
  rtsp_url: string;
  is_active: boolean;
}

export interface Zone {
  id: number;
  camera_id: number;
  coordinates: number[][];
}

export interface Incident {
  id: number;
  camera_id: number;
  type: IncidentType;
  timestamp: string;
  image_path: string;
}

export interface IncidentListResponse {
  items: Incident[];
  page: number;
  page_size: number;
  total: number;
}

export interface WsIncidentCreatedPayload {
  event: "incident_created";
  data: Incident;
}

