"use client";

import React, { useEffect, useState, useRef } from 'react';
import { Bot, Database, Download, FileSpreadsheet, RefreshCw, CheckCircle, Search, Rocket, Loader2, Upload, Link } from 'lucide-react';
import toast, { Toaster } from 'react-hot-toast';
import * as api from '../services/api';

export default function Dashboard() {
  const [status, setStatus] = useState<api.AppStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [numWorkers, setNumWorkers] = useState(0);
  const [numLinkWorkers, setNumLinkWorkers] = useState(0);
  const [sortOrder, setSortOrder] = useState<'low_to_high' | 'high_to_low'>('low_to_high');
  const [isExporting, setIsExporting] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isUploadingLinks, setIsUploadingLinks] = useState(false);
  const [importedCount, setImportedCount] = useState<number | null>(null);
  const [productDetailCount, setProductDetailCount] = useState<number>(0);
  const [searchCount, setSearchCount] = useState<number>(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const linksFileInputRef = useRef<HTMLInputElement>(null);

  // Refs to track previous status for completion detection
  const prevLinkRunning = useRef<boolean>(false);
  const prevScrapeRunning = useRef<boolean>(false);
  const prevLinkExtractionRunning = useRef<boolean>(false);

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
      if (prevLinkExtractionRunning.current && !data.is_link_extraction_running) {
         toast.success("Link Extraction completed successfully!", { duration: 5000 });
      }

      prevLinkRunning.current = data.is_link_generation_running;
      prevScrapeRunning.current = data.is_scraping_running;
      prevLinkExtractionRunning.current = data.is_link_extraction_running;

      setStatus(data);

      // Fetch import status alongside
      try {
        const importData = await api.getImportStatus();
        setImportedCount(importData.imported_parts_count);
        setProductDetailCount(importData.product_detail_count);
        setSearchCount(importData.search_count);
      } catch { /* ignore if endpoint not available */ }

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
      toast.loading("Initiating Full Link Generation...", { id: 'linkGen' });
      await api.startLinkGeneration({ mode: 'full' });
      toast.success("Link Generation queued successfully!", { id: 'linkGen' });
      fetchStatus();
    } catch (err: any) {
      toast.error(`Error queueing Link Generation: ${err?.response?.data?.detail || err.message}`, { id: 'linkGen' });
    }
  };

  const handleScraping = async () => {
    try {
      const workers = numWorkers > 0 ? numWorkers : undefined;
      toast.loading(`Initiating Full Selenium Scraper${workers ? ` (${workers} workers)` : ''}...`, { id: 'scrape' });
      await api.startScraping({ mode: 'full', num_workers: workers, sort_order: sortOrder });
      toast.success("Selenium Scraping queued successfully!", { id: 'scrape' });
      fetchStatus();
    } catch (err: any) {
      toast.error(`Error queueing Scraping: ${err?.response?.data?.detail || err.message}`, { id: 'scrape' });
    }
  };

  const handleStopLinkGen = async () => {
    try {
      toast.loading("Sending stop signal to Link Engine...", { id: 'linkGenStop' });
      await api.stopLinkGeneration();
      toast.success("Stop signal received. Terminating shortly.", { id: 'linkGenStop' });
      fetchStatus();
    } catch (err: any) {
      toast.error(`Stop failed: ${err.message}`, { id: 'linkGenStop' });
    }
  };

  const handleStopScraping = async () => {
    try {
      toast.loading("Sending stop signal to Selenium Scraper...", { id: 'scrapeStop' });
      await api.stopScraping();
      toast.success("Stop signal received. Driver will close soon.", { id: 'scrapeStop' });
      fetchStatus();
    } catch (err: any) {
      toast.error(`Stop failed: ${err.message}`, { id: 'scrapeStop' });
    }
  };

  const handleLinkExtraction = async () => {
    try {
      const workers = numLinkWorkers > 0 ? numLinkWorkers : undefined;
      toast.loading(`Initiating Link Extraction${workers ? ` (${workers} workers)` : ''}...`, { id: 'linkExtract' });
      await api.startLinkExtraction({ sort_order: sortOrder, num_workers: workers });
      toast.success("Link Extraction queued successfully!", { id: 'linkExtract' });
      fetchStatus();
    } catch (err: any) {
      toast.error(`Error starting Link Extraction: ${err?.response?.data?.detail || err.message}`, { id: 'linkExtract' });
    }
  };

  const handleStopLinkExtraction = async () => {
    try {
      toast.loading("Sending stop signal to Link Extractor...", { id: 'linkExtractStop' });
      await api.stopLinkExtraction();
      toast.success("Stop signal received. Extractor will close soon.", { id: 'linkExtractStop' });
      fetchStatus();
    } catch (err: any) {
      toast.error(`Stop failed: ${err.message}`, { id: 'linkExtractStop' });
    }
  };

  const handleExport = async () => {
    try {
      setIsExporting(true);

      // Check what data is available before downloading
      const info = await api.getExportInfo();

      if (info.active_engine === 'none') {
        toast.error(
          "No scraped data found. Run Price Extraction or Link Extraction first.",
          { id: 'export', duration: 5000 }
        );
        return;
      }

      const engineLabels: Record<string, string> = {
        parts: `Price Extraction data (${info.parts_records.toLocaleString()} records)`,
        links: `Link Extraction data (${info.links_records.toLocaleString()} records)`,
        both:  `Price Extraction (${info.parts_records.toLocaleString()} records) + Link Extraction (${info.links_records.toLocaleString()} records)`,
      };

      toast.loading(
        `Compiling ${engineLabels[info.active_engine] ?? 'data'}...`,
        { id: 'export' }
      );

      await api.downloadExport();

      const successLabels: Record<string, string> = {
        parts: "GSA Parts Data sheet downloaded successfully!",
        links: "Links Scraped Data sheet downloaded successfully!",
        both:  "Full export (both sheets) downloaded successfully!",
      };

      toast.success(
        successLabels[info.active_engine] ?? "Excel file downloaded successfully!",
        { id: 'export', duration: 5000 }
      );
    } catch (err: any) {
      toast.error(
        `Export failed: ${err?.response?.data?.detail || err.message}`,
        { id: 'export' }
      );
    } finally {
      setIsExporting(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      setIsUploading(true);
      toast.loading("Uploading and importing parts data...", { id: 'import' });
      const result = await api.uploadParts(file);
      setImportedCount(result.rows_imported);
      toast.success(`Imported ${result.rows_imported.toLocaleString()} parts from ${result.filename}`, { id: 'import', duration: 5000 });
      fetchStatus();
    } catch (err: any) {
      toast.error(`Import failed: ${err?.response?.data?.detail || err.message}`, { id: 'import' });
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleLinksUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      setIsUploadingLinks(true);
      toast.loading("Uploading and importing links data...", { id: 'importLinks' });
      const result = await api.uploadLinks(file);
      toast.success(
        `Imported ${result.rows_imported.toLocaleString()} links (${result.product_detail_links} product detail, ${result.search_links} search)`,
        { id: 'importLinks', duration: 5000 }
      );
      fetchStatus();
    } catch (err: any) {
      toast.error(`Import failed: ${err?.response?.data?.detail || err.message}`, { id: 'importLinks' });
    } finally {
      setIsUploadingLinks(false);
      if (linksFileInputRef.current) linksFileInputRef.current.value = '';
    }
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
          
          <div className="flex flex-wrap items-center gap-4">
            {/* Server Status Radar */}
            <div className="flex items-center gap-2">
              <span className="flex h-2.5 w-2.5 relative">
                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${error ? 'bg-red-400' : 'bg-emerald-400'}`}></span>
                <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${error ? 'bg-red-500' : 'bg-emerald-500'}`}></span>
              </span>
              <span className={`text-sm font-semibold tracking-wide ${error ? 'text-red-600' : 'text-slate-700'}`}>
                {error ? 'Disconnected' : 'Server Online'}
              </span>
            </div>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-xl flex items-center gap-3 shadow-sm">
            <Database className="w-5 h-5 flex-shrink-0" />
            <p className="text-sm font-medium">{error}</p>
          </div>
        )}

        {/* Dynamic Database Statistics */}
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <StatCard
            title="Imported Parts"
            value={importedCount ?? 0}
            icon={<Upload className="w-5 h-5" />}
            color="text-amber-600"
            bg="bg-amber-50 border border-amber-100"
          />
          <StatCard
            title="Product Detail Links"
            value={productDetailCount}
            icon={<FileSpreadsheet className="w-5 h-5" />}
            color="text-indigo-600"
            bg="bg-indigo-50 border border-indigo-100"
          />
          <StatCard
            title="Search Links"
            value={searchCount}
            icon={<Search className="w-5 h-5" />}
            color="text-cyan-600"
            bg="bg-cyan-50 border border-cyan-100"
          />
          <StatCard
            title="Generated URL Links"
            value={status?.database.total_generated_links_count}
            icon={<Link className="w-5 h-5" />}
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

        {/* Import Section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Import Parts */}
          <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6 relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-amber-50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
            <div className="flex flex-col gap-4 relative z-10">
              <div>
                <h2 className="text-xl font-bold flex items-center gap-2 text-slate-800">
                  <Upload className="w-5 h-5 text-amber-600" />
                  Import Parts
                </h2>
                <p className="text-slate-500 text-sm mt-1">
                  Upload an Excel file with <code className="bg-slate-100 px-1.5 py-0.5 rounded text-xs font-mono">part_number</code> and <code className="bg-slate-100 px-1.5 py-0.5 rounded text-xs font-mono">manufacturer</code> columns.
                </p>
              </div>
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".xlsx,.xls"
                  onChange={handleFileUpload}
                  className="hidden"
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploading || status?.is_link_generation_running || status?.is_scraping_running}
                  className="w-full flex items-center justify-center gap-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 disabled:hover:bg-amber-500 text-white font-semibold px-5 py-3 rounded-xl transition-all shadow-md active:scale-[0.98]"
                >
                  {isUploading ? (
                    <><Loader2 className="w-5 h-5 animate-spin" /> Importing...</>
                  ) : (
                    <><Upload className="w-5 h-5" /> Upload Parts .XLSX</>
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* Import Links */}
          <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6 relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-indigo-50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
            <div className="flex flex-col gap-4 relative z-10">
              <div>
                <h2 className="text-xl font-bold flex items-center gap-2 text-slate-800">
                  <Link className="w-5 h-5 text-indigo-600" />
                  Import Links
                </h2>
                <p className="text-slate-500 text-sm mt-1">
                  Accepts: <code className="bg-slate-100 px-1.5 py-0.5 rounded text-xs font-mono">Internal Link URL</code> column, or <code className="bg-slate-100 px-1.5 py-0.5 rounded text-xs font-mono">Manufacturer Part Number</code> + <code className="bg-slate-100 px-1.5 py-0.5 rounded text-xs font-mono">External Link URL</code>.
                </p>
              </div>
              <div>
                <input
                  ref={linksFileInputRef}
                  type="file"
                  accept=".xlsx,.xls"
                  onChange={handleLinksUpload}
                  className="hidden"
                />
                <button
                  onClick={() => linksFileInputRef.current?.click()}
                  disabled={isUploadingLinks || status?.is_link_generation_running || status?.is_scraping_running}
                  className="w-full flex items-center justify-center gap-2 bg-indigo-500 hover:bg-indigo-600 disabled:opacity-50 disabled:hover:bg-indigo-500 text-white font-semibold px-5 py-3 rounded-xl transition-all shadow-md active:scale-[0.98]"
                >
                  {isUploadingLinks ? (
                    <><Loader2 className="w-5 h-5 animate-spin" /> Importing...</>
                  ) : (
                    <><Link className="w-5 h-5" /> Upload Links .XLSX</>
                  )}
                </button>
              </div>
            </div>
          </div>
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

              <div className="bg-slate-50 border border-slate-200 p-4 rounded-xl text-slate-600 text-sm font-medium flex items-center gap-3">
                <Rocket className="w-5 h-5 text-slate-400" />
                Generates GSA Advantage URLs for all imported part numbers.
              </div>

                <div className="flex gap-2 mt-4">
                  <button 
                    onClick={handleLinkGeneration}
                    disabled={status?.is_link_generation_running || !!error}
                    className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:hover:bg-blue-600 text-white font-semibold px-4 py-3 rounded-xl transition-all shadow-md active:scale-[0.98]"
                  >
                    {status?.is_link_generation_running ? (
                      <><Loader2 className="w-5 h-5 animate-spin" /> Link Engine Active...</>
                    ) : (
                      <><Search className="w-5 h-5" /> Launch URL Extractor</>
                    )}
                  </button>
                  
                  {status?.is_link_generation_running && (
                    <button 
                      onClick={handleStopLinkGen}
                      className="bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 font-bold px-6 py-3 rounded-xl transition-all active:scale-95"
                      title="Forcibly stop link generation"
                    >
                      Stop
                    </button>
                  )}
                </div>
            </div>
          </div>

          {/* Scraping Panel */}
          <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6 relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-emerald-50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold flex items-center gap-2 text-slate-800">
                <Bot className="w-5 h-5 text-emerald-600" />
                Phase 2: Selenium Scraper
              </h2>
              <div className="flex items-center gap-2">
                {status?.is_scraping_running && (
                  <span className="flex items-center gap-2 text-xs font-semibold bg-emerald-50 text-emerald-700 px-3 py-1 rounded-full border border-emerald-200">
                    <RefreshCw className="w-3 h-3 animate-spin" /> Scraping...
                  </span>
                )}
                {status?.is_link_extraction_running && (
                  <span className="flex items-center gap-2 text-xs font-semibold bg-indigo-50 text-indigo-700 px-3 py-1 rounded-full border border-indigo-200">
                    <RefreshCw className="w-3 h-3 animate-spin" /> Extracting Links...
                  </span>
                )}
              </div>
            </div>

            <div className="space-y-0 relative z-10">

              {/* Shared: Price Sort */}
              <div className="flex flex-col gap-2 pb-4">
                <label className="text-xs uppercase font-bold text-slate-500 tracking-wider">Price Sort (shared)</label>
                <select
                  value={sortOrder}
                  onChange={(e) => setSortOrder(e.target.value as 'low_to_high' | 'high_to_low')}
                  disabled={status?.is_scraping_running || status?.is_link_extraction_running}
                  className="bg-white border text-slate-700 font-medium border-slate-200 text-sm rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:border-transparent focus:ring-emerald-500/50 shadow-sm transition-all disabled:opacity-50"
                >
                  <option value="low_to_high">Low to High</option>
                  <option value="high_to_low">High to Low</option>
                </select>
              </div>

              {/* ── Price Extraction sub-section ──────────────────────────── */}
              <div className="border-t border-slate-100 pt-4 space-y-3">
                <p className="text-xs uppercase font-bold text-emerald-700 tracking-wider flex items-center gap-1.5">
                  <CheckCircle className="w-3.5 h-3.5" /> Price Extraction — works on Import Parts
                </p>

                <div className="flex flex-col gap-2">
                  <label className="text-xs uppercase font-bold text-slate-500 tracking-wider">Parallel Workers</label>
                  <select
                    value={numWorkers}
                    onChange={(e) => setNumWorkers(Number(e.target.value))}
                    disabled={status?.is_scraping_running}
                    className="bg-white border text-slate-700 font-medium border-slate-200 text-sm rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:border-transparent focus:ring-emerald-500/50 shadow-sm transition-all disabled:opacity-50"
                  >
                    <option value={0}>Auto-detect</option>
                    <option value={1}>1 Worker</option>
                    <option value={2}>2 Workers</option>
                    <option value={3}>3 Workers</option>
                    <option value={4}>4 Workers</option>
                    <option value={5}>5 Workers</option>
                  </select>
                </div>

                {status?.scraping_progress && status.is_scraping_running && (
                  <ScrapingProgressPanel progress={status.scraping_progress} colorClass="emerald" />
                )}

                <div className="flex gap-2">
                  <button
                    onClick={handleScraping}
                    disabled={status?.is_scraping_running || status?.is_link_extraction_running || !!error}
                    className="flex-1 flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:hover:bg-emerald-600 text-white font-semibold px-4 py-3 rounded-xl transition-all shadow-md active:scale-[0.98]"
                  >
                    {status?.is_scraping_running ? (
                      <><Loader2 className="w-5 h-5 animate-spin" /> Running Selenium...</>
                    ) : (
                      <><CheckCircle className="w-5 h-5" /> Start Price Extraction</>
                    )}
                  </button>
                  {status?.is_scraping_running && (
                    <button
                      onClick={handleStopScraping}
                      className="bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 font-bold px-6 py-3 rounded-xl transition-all active:scale-95"
                    >
                      Stop
                    </button>
                  )}
                </div>
              </div>

              {/* ── Link Extraction sub-section ───────────────────────────── */}
              <div className="border-t border-slate-100 pt-4 space-y-3">
                <p className="text-xs uppercase font-bold text-indigo-700 tracking-wider flex items-center gap-1.5">
                  <Link className="w-3.5 h-3.5" /> Link Extraction — works on Import Links
                </p>

                <div className="flex flex-col gap-2">
                  <label className="text-xs uppercase font-bold text-slate-500 tracking-wider">Parallel Workers</label>
                  <select
                    value={numLinkWorkers}
                    onChange={(e) => setNumLinkWorkers(Number(e.target.value))}
                    disabled={status?.is_link_extraction_running}
                    className="bg-white border text-slate-700 font-medium border-slate-200 text-sm rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:border-transparent focus:ring-indigo-500/50 shadow-sm transition-all disabled:opacity-50"
                  >
                    <option value={0}>Auto-detect</option>
                    <option value={1}>1 Worker</option>
                    <option value={2}>2 Workers</option>
                    <option value={3}>3 Workers</option>
                    <option value={4}>4 Workers</option>
                    <option value={5}>5 Workers</option>
                  </select>
                </div>

                {status?.link_extraction_progress && status.is_link_extraction_running && (
                  <ScrapingProgressPanel progress={status.link_extraction_progress} colorClass="indigo" />
                )}

                <div className="flex gap-2">
                  <button
                    onClick={handleLinkExtraction}
                    disabled={status?.is_link_extraction_running || status?.is_scraping_running || !!error}
                    className="flex-1 flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:hover:bg-indigo-600 text-white font-semibold px-4 py-3 rounded-xl transition-all shadow-md active:scale-[0.98]"
                  >
                    {status?.is_link_extraction_running ? (
                      <><Loader2 className="w-5 h-5 animate-spin" /> Extracting Links...</>
                    ) : (
                      <><Link className="w-5 h-5" /> Start Link Extraction</>
                    )}
                  </button>
                  {status?.is_link_extraction_running && (
                    <button
                      onClick={handleStopLinkExtraction}
                      className="bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 font-bold px-6 py-3 rounded-xl transition-all active:scale-95"
                    >
                      Stop
                    </button>
                  )}
                </div>
              </div>

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
              disabled={isExporting || !!error}
              className="group whitespace-nowrap flex items-center justify-center min-w-[240px] gap-3 bg-white hover:bg-slate-100 disabled:bg-slate-50 disabled:text-slate-400 disabled:cursor-not-allowed text-slate-900 font-bold px-6 py-3.5 rounded-xl transition-all shadow-lg active:scale-95"
            >
              {isExporting ? (
                <><Loader2 className="w-5 h-5 animate-spin text-blue-500" /> Compiling Data...</>
              ) : (
                <><Download className="w-5 h-5 group-hover:-translate-y-0.5 transition-transform" /> Download Final .XLSX</>
              )}
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

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

const PROGRESS_PANEL_STYLES: Record<string, { bg: string; border: string; bar: string; barTrack: string; textBold: string; textMid: string; workerBorder: string; workerText: string; workerSubText: string }> = {
  emerald: {
    bg: "bg-emerald-50",
    border: "border-emerald-200",
    bar: "bg-emerald-500",
    barTrack: "bg-emerald-100",
    textBold: "text-emerald-800",
    textMid: "text-emerald-700",
    workerBorder: "border-emerald-100",
    workerText: "text-emerald-800",
    workerSubText: "text-emerald-600",
  },
  indigo: {
    bg: "bg-indigo-50",
    border: "border-indigo-200",
    bar: "bg-indigo-500",
    barTrack: "bg-indigo-100",
    textBold: "text-indigo-800",
    textMid: "text-indigo-700",
    workerBorder: "border-indigo-100",
    workerText: "text-indigo-800",
    workerSubText: "text-indigo-600",
  },
};

function ScrapingProgressPanel({ progress, colorClass = "emerald" }: { progress: api.ScrapingProgress; colorClass?: string }) {
  const pct = progress.total > 0 ? Math.round((progress.completed / progress.total) * 100) : 0;
  const s = PROGRESS_PANEL_STYLES[colorClass] ?? PROGRESS_PANEL_STYLES.emerald;

  return (
    <div className={`${s.bg} border ${s.border} rounded-xl p-4 space-y-3`}>
      <div className={`w-full h-2.5 ${s.barTrack} rounded-full overflow-hidden`}>
        <div
          className={`h-full ${s.bar} rounded-full transition-all duration-1000 ease-in-out`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className={`flex flex-wrap items-center justify-between text-xs font-semibold ${s.textBold} gap-2`}>
        <span>{progress.completed.toLocaleString()} / {progress.total.toLocaleString()} rows ({pct}%)</span>
        <span>{progress.active_workers} / {progress.num_workers} workers active</span>
      </div>

      <div className={`flex flex-wrap items-center justify-between text-xs ${s.textMid} gap-2`}>
        <span>{progress.successful.toLocaleString()} matched &middot; {progress.failed.toLocaleString()} failed</span>
        <span>
          {progress.avg_seconds_per_row > 0 && `${progress.avg_seconds_per_row}s/row`}
          {progress.estimated_remaining_seconds > 0 && ` · ETA: ${formatDuration(progress.estimated_remaining_seconds)}`}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5 pt-1">
        {progress.workers.map((w) => (
          <div key={w.id} className={`bg-white/60 border ${s.workerBorder} rounded-lg px-2.5 py-1.5 text-xs`}>
            <div className={`font-bold ${s.workerText}`}>Worker {w.id + 1}</div>
            <div className={`${s.workerSubText} truncate`}>
              {w.completed} done · <span className="capitalize">{w.status}</span>
            </div>
          </div>
        ))}
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