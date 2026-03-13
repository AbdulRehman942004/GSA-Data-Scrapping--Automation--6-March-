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

export const stopLinkGeneration = async () => {
  const response = await api.post('/api/links/stop');
  return response.data;
};

export const stopScraping = async () => {
  const response = await api.post('/api/scrape/stop');
  return response.data;
};


export const downloadExport = async () => {
  // Use axios instead of window location so we can await the download completion for loading states
  const response = await api.get('/api/export', { responseType: 'blob' });
  
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement('a');
  link.href = url;
  
  let filename = 'GSA_Export.xlsx';
  const contentDisposition = response.headers['content-disposition'];
  if (contentDisposition) {
    const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
    if (filenameMatch && filenameMatch.length > 1) {
      filename = filenameMatch[1];
    }
  }
  
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  link?.parentNode?.removeChild(link);
  window.URL.revokeObjectURL(url);
};

