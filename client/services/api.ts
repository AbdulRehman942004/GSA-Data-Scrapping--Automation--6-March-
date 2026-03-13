import axios from 'axios';

const SERVER_URL = process.env.NEXT_PUBLIC_SERVER_URL || 'http://localhost:8000';

export interface LinkGenerationRequest {
  mode: 'test' | 'full' | 'custom';
  item_limit?: number;
  start_row?: number;
  end_row?: number;
}

export interface ScrapingRequest {
  mode: 'test' | 'full' | 'missing' | 'custom';
  item_limit?: number;
  start_row?: number;
  end_row?: number;
}

export interface DatabaseStatus {
  total_generated_links_count: number;
  total_successfully_scraped_links_count: number;
  total_scraped_data_records: number;
}

export interface AppStatus {
  is_link_generation_running: boolean;
  is_scraping_running: boolean;
  database: DatabaseStatus;
}

const api = axios.create({
  baseURL: SERVER_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const getStatus = async (): Promise<AppStatus> => {
  const response = await api.get<AppStatus>('/api/status');
  return response.data;
};

export const startLinkGeneration = async (data: LinkGenerationRequest) => {
  const response = await api.post('/api/links/generate', data);
  return response.data;
};

export const startScraping = async (data: ScrapingRequest) => {
  const response = await api.post('/api/scrape/start', data);
  return response.data;
};

export const downloadExport = () => {
  // Instead of an axios call, just directly hit the endpoint to trigger the browser's native file download dialog.
  window.open(`${SERVER_URL}/api/export`, '_blank');
};
