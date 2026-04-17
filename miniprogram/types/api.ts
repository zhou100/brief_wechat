export type MiniappUser = {
  id: string;
  display_name?: string;
};

export type LoginResponse = {
  token: string;
  user: MiniappUser;
};

export type UploadCreateResponse = {
  upload_api_url: string;
  object_key: string;
  headers?: Record<string, string>;
};

export type CloudUploadResponse = {
  cloud_file_id: string;
  cloud_temp_url: string;
  cloud_path: string;
};

export type EntryCreateResponse = {
  entry_id: string;
  job_id: string;
};

export type JobStatus = "queued" | "processing" | "done" | "failed";

export type JobResponse = {
  job_id: string;
  entry_id?: string;
  status: JobStatus;
  progress?: number;
  step?: string;
  error_code?: string;
  error_message?: string;
  result_preview?: {
    summary?: string;
  };
};

export type CategoryItem = {
  id?: string;
  text?: string;
  category: "EARNING" | "LEARNING" | "RELAXING" | "FAMILY" | "TODO" | "EXPERIMENT" | "REFLECTION" | "TIME_RECORD";
  estimated_minutes?: number;
};

export type DailyBrief = {
  entry_id: string;
  result_id?: string;
  cloud_file_id?: string;
  created_at: string;
  summary: string;
  key_points: string[];
  open_loops: string[];
  share_card?: ShareCard;
};

export type HistoryItem = {
  id: string;
  transcript?: string;
  local_date?: string;
  created_at: string;
  duration_seconds?: number;
  categories: CategoryItem[];
};

export type HistoryResponse = {
  items: HistoryItem[];
  total: number;
  skip: number;
  limit: number;
};

export type ShareCard = {
  share_id: string;
  title: string;
  summary: string;
  open_loop_count: number;
  image_url?: string;
};

export type ShareCardResponse = {
  card: ShareCard;
};

export type SharedBrief = {
  share_id: string;
  summary: string;
  open_loop_count: number;
  created_at: string;
};
