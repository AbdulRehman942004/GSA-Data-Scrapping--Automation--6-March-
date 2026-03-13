"use client";

import React, { useEffect, useState, useRef } from 'react';
import { Bot, Database, Download, FileSpreadsheet, RefreshCw, CheckCircle, Search, Rocket, Loader2 } from 'lucide-react';
import toast, { Toaster } from 'react-hot-toast';
import * as api from '../services/api';

export default function Dashboard() {
  const [status, setStatus] = useState<api.AppStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form states
  const [linkMode, setLinkMode] = useState<'test' | 'full' | 'custom'>('test');
  const [scrapeMode, setScrapeMode] = useState<'test' | 'full' | 'missing' | 'custom'>('test');
  const [itemLimit, setItemLimit] = useState(5);

  // Refs to track previous status for completion detection
  const prevLinkRunning = useRef<boolean>(false);
  const prevScrapeRunning = useRef<boolean>(false);

  const fetchStatus = async () => {
    try {
      const data = await api.getStatus();
      
      // Detection logic for checking if something JUST finished
      if (prevLinkRunning.current && !data.is_link_generation_running) {
         toast.success("Link Generation Phase completed successfully!", { duration: 5000 });
      }
      if (prevScrapeRunning.current && !data.is_scraping_running) {
         toast.success("Web Scraping Phase completed successfully!", { duration: 5000 });
      }
      
      prevLinkRunning.current = data.is_link_generation_running;
      prevScrapeRunning.current = data.is_scraping_running;

      setStatus(data);
      if (error) {
        toast.success("Server re-connected!");
        setError(null);
      }
    } catch (err: any) {
      console.error("Failed to fetch status:", err);
      setError("Unable to connect to GSA Automation Server. Is FastAPI running?");
    } finally {
      setLoading(false);
    }
  };

  // Poll status every 3 seconds
  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleLinkGeneration = async () => {
    try {
      toast.loading("Initiating Link Generation...", { id: 'linkGen' });
      await api.startLinkGeneration({ mode: linkMode, item_limit: itemLimit });
      toast.success("Link Generation queued successfully!", { id: 'linkGen' });
      fetchStatus();
    } catch (err: any) {
      toast.error(`Error queueing Link Generation: ${err?.response?.data?.detail || err.message}`, { id: 'linkGen' });
    }
  };

  const handleScraping = async () => {
    try {
      toast.loading("Initiating Selenium Scraper...", { id: 'scrape' });
      await api.startScraping({ mode: scrapeMode, item_limit: itemLimit });
      toast.success("Selenium Scraping queued successfully!", { id: 'scrape' });
      fetchStatus();
    } catch (err: any) {
      toast.error(`Error queueing Scraping: ${err?.response?.data?.detail || err.message}`, { id: 'scrape' });
    }
  };

  const handleExport = () => {
    toast.success("Beginning data compilation and download...");
    api.downloadExport();
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans p-8 selection:bg-blue-500/30">
      <Toaster position="top-right" reverseOrder={false} />
      
      <div className="max-w-6xl mx-auto space-y-8">
        
        {/* Header */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center border-b border-slate-200 pb-6 gap-4">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight flex items-center gap-3 text-slate-800">
              <Bot className="w-8 h-8 text-blue-600" />
              GSA Scraper Operations
            </h1>
            <p className="text-slate-500 mt-2 text-sm">Automated pipeline control center for GSA Advantage Pricing</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="flex h-3 w-3 relative">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${error ? 'bg-red-400' : 'bg-emerald-400'}`}></span>
              <span className={`relative inline-flex rounded-full h-3 w-3 ${error ? 'bg-red-500' : 'bg-emerald-500'}`}></span>
            </span>
            <span className={`text-sm font-semibold tracking-wide ${error ? 'text-red-600' : 'text-slate-700'}`}>{error ? 'Disconnected' : 'Server Online'}</span>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-xl flex items-center gap-3 shadow-sm">
            <Database className="w-5 h-5 flex-shrink-0" />
            <p className="text-sm font-medium">{error}</p>
          </div>
        )}

        {/* Dynamic Database Statistics */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <StatCard 
            title="Generated URL Links" 
            value={status?.database.total_generated_links_count} 
            icon={<Search className="w-5 h-5" />} 
            color="text-blue-600"
            bg="bg-blue-50 border border-blue-100"
          />
          <StatusStatCard 
            title="Extraction Status" 
            completed={status?.database.total_successfully_scraped_links_count} 
            total={status?.database.total_generated_links_count}
            icon={<CheckCircle className="w-5 h-5" />} 
            color="text-emerald-600"
            bg="bg-emerald-50 border border-emerald-100"
            fill="bg-emerald-500"
          />
          <StatCard 
            title="Extracted Pricing Records" 
            value={status?.database.total_scraped_data_records} 
            icon={<Database className="w-5 h-5" />} 
            color="text-purple-600"
            bg="bg-purple-50 border border-purple-100"
          />
        </div>

        {/* Process Controls */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-4">
          
          {/* Link Generation Panel */}
          <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6 relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-blue-50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
            
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold flex items-center gap-2 text-slate-800">
                <Rocket className="w-5 h-5 text-blue-600" />
                Phase 1: Generative Engine
              </h2>
              {status?.is_link_generation_running && (
                <span className="flex items-center gap-2 text-xs font-semibold bg-blue-50 text-blue-700 px-3 py-1 rounded-full border border-blue-200">
                  <RefreshCw className="w-3 h-3 animate-spin" /> Running
                </span>
              )}
            </div>

            <div className="space-y-4 relative z-10">
              <div className="flex flex-col gap-2">
                <label className="text-xs uppercase font-bold text-slate-500 tracking-wider">Operation Mode</label>
                <select 
                  className="bg-white border text-slate-700 font-medium border-slate-200 text-sm rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:border-transparent focus:ring-blue-500/50 shadow-sm transition-all"
                  value={linkMode}
                  onChange={(e) => setLinkMode(e.target.value as any)}
                  disabled={status?.is_link_generation_running}
                >
                  <option value="test">Test Mode (Limited Items)</option>
                  <option value="full">Super Fast Automation (Full Data)</option>
                </select>
              </div>

              {linkMode === 'test' && (
                <div className="flex flex-col gap-2">
                  <label className="text-xs uppercase font-bold text-slate-500 tracking-wider">Test Sample Limit</label>
                  <input 
                    type="number" 
                    value={itemLimit}
                    onChange={(e) => setItemLimit(Number(e.target.value))}
                    min={1} max={100}
                    className="bg-white border text-slate-700 font-medium border-slate-200 text-sm rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:border-transparent focus:ring-blue-500/50 shadow-sm transition-all"
                  />
                </div>
              )}

              <button 
                onClick={handleLinkGeneration}
                disabled={status?.is_link_generation_running || !!error}
                className="w-full mt-4 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:hover:bg-blue-600 text-white font-semibold px-4 py-3 rounded-xl transition-all shadow-md active:scale-[0.98]"
              >
                {status?.is_link_generation_running ? (
                  <><Loader2 className="w-5 h-5 animate-spin" /> Link Engine Active...</>
                ) : (
                  <><Search className="w-5 h-5" /> Launch URL Extractor</>
                )}
              </button>
            </div>
          </div>

          {/* Scraping Panel */}
          <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6 relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-emerald-50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
            
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold flex items-center gap-2 text-slate-800">
                <Bot className="w-5 h-5 text-emerald-600" />
                Phase 2: Selenium Scraper
              </h2>
              {status?.is_scraping_running && (
                <span className="flex items-center gap-2 text-xs font-semibold bg-emerald-50 text-emerald-700 px-3 py-1 rounded-full border border-emerald-200">
                  <RefreshCw className="w-3 h-3 animate-spin" /> Scraping actively...
                </span>
              )}
            </div>

            <div className="space-y-4 relative z-10">
              <div className="flex flex-col gap-2">
                <label className="text-xs uppercase font-bold text-slate-500 tracking-wider">Operation Mode</label>
                <select 
                  className="bg-white border text-slate-700 font-medium border-slate-200 text-sm rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:border-transparent focus:ring-emerald-500/50 shadow-sm transition-all"
                  value={scrapeMode}
                  onChange={(e) => setScrapeMode(e.target.value as any)}
                  disabled={status?.is_scraping_running}
                >
                  <option value="test">Test Mode (First Records)</option>
                  <option value="full">Full Scrape Workflow</option>
                  <option value="missing">Fill Missing Records Extractor</option>
                </select>
              </div>

              {scrapeMode === 'test' && (
                <div className="flex flex-col gap-2">
                  <label className="text-xs uppercase font-bold text-slate-500 tracking-wider">Test Sample Limit</label>
                  <input 
                    type="number" 
                    value={itemLimit}
                    onChange={(e) => setItemLimit(Number(e.target.value))}
                    min={1} max={100}
                    className="bg-white border text-slate-700 font-medium border-slate-200 text-sm rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:border-transparent focus:ring-emerald-500/50 shadow-sm transition-all"
                  />
                </div>
              )}

              <button 
                onClick={handleScraping}
                disabled={status?.is_scraping_running || !!error}
                className="w-full mt-4 flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:hover:bg-emerald-600 text-white font-semibold px-4 py-3 rounded-xl transition-all shadow-md active:scale-[0.98]"
              >
                {status?.is_scraping_running ? (
                  <><Loader2 className="w-5 h-5 animate-spin" /> Running Selenium...</>
                ) : (
                  <><CheckCircle className="w-5 h-5" /> Start Price Extraction</>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Database Export Center */}
        <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 mt-6 shadow-md text-white">
          <div className="flex flex-col md:flex-row items-center justify-between gap-6">
            <div className="text-center md:text-left">
              <h2 className="text-xl font-bold mb-2 flex items-center justify-center md:justify-start gap-2 text-white">
                <FileSpreadsheet className="w-5 h-5 text-blue-400" />
                Final Output Generation
              </h2>
              <p className="text-slate-300 text-sm max-w-xl">
                Ready to deliver? Generate a real-time Excel spreadsheet syncing the blank template items directly against the newly obtained Postgres scraping data.
              </p>
            </div>
            <button 
              onClick={handleExport}
              className="group whitespace-nowrap flex items-center gap-3 bg-white hover:bg-slate-100 text-slate-900 font-bold px-6 py-3.5 rounded-xl transition-all shadow-lg active:scale-95"
            >
              <Download className="w-5 h-5 group-hover:-translate-y-0.5 transition-transform" /> 
              Download Final .XLSX
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}

function StatCard({ title, value, icon, color, bg }: { title: string, value?: number, icon: React.ReactNode, color: string, bg: string }) {
  return (
    <div className="bg-white shadow-sm border border-slate-200 rounded-2xl p-5 flex flex-col justify-between">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-500">{title}</h3>
        <div className={`p-2 rounded-lg ${bg} ${color}`}>
          {icon}
        </div>
      </div>
      <div>
        {value === undefined ? (
           <div className="h-9 w-24 bg-slate-100 animate-pulse rounded-lg" />
        ) : (
          <span className="text-4xl font-black tracking-tight text-slate-800">{value.toLocaleString()}</span>
        )}
      </div>
    </div>
  );
}

function StatusStatCard({ title, completed, total, icon, color, bg, fill }: { title: string, completed?: number, total?: number, icon: React.ReactNode, color: string, bg: string, fill: string }) {
  const percentage = (total && completed) ? Math.round((completed / total) * 100) : 0;
  
  return (
    <div className="bg-white shadow-sm border border-slate-200 rounded-2xl p-5 flex flex-col justify-between relative overflow-hidden group">
       <div className="absolute top-0 left-0 w-full h-1 bg-slate-100">
         <div className={`h-full ${fill}`} style={{ width: `${percentage}%`, transition: 'width 1s ease-in-out' }} />
       </div>
      <div className="flex items-center justify-between mt-2 mb-4">
        <h3 className="text-sm font-semibold text-slate-500">{title}</h3>
        <div className={`p-2 rounded-lg ${bg} ${color} flex items-center gap-2`}>
          {icon}
        </div>
      </div>
      <div className="flex items-baseline gap-2">
        {completed === undefined ? (
          <div className="h-9 w-32 bg-slate-100 animate-pulse rounded-lg" />
        ) : (
          <>
            <span className="text-4xl font-black tracking-tight text-slate-800">{completed.toLocaleString()}</span>
            <span className="text-sm text-slate-400 font-semibold">/ {total?.toLocaleString()}</span>
          </>
        )}
      </div>
    </div>
  );
}