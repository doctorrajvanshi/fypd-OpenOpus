import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Settings, 
  Play, 
  Globe, 
  Cpu, 
  Clock, 
  Video,
  Smartphone,
  ExternalLink,
  Copy,
  RefreshCw,
  Key,
  Share2,
  Server,
  Zap,
  X,
  Volume2,
  Download,
  Check,
  Sparkles
} from 'lucide-react';
import axios from 'axios';

import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { check } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";

const API_BASE = (window.location.port === '5173' || window.location.origin.includes('tauri') || window.location.protocol === 'file:')
  ? 'http://127.0.0.1:8000'
  : window.location.origin;

const Logo = () => (
  <div className="relative group">
    <motion.div 
      animate={{ 
        boxShadow: ["0 0 0px rgba(255,255,0,0)", "0 0 20px rgba(255,255,0,0.2)", "0 0 0px rgba(255,255,0,0)"]
      }}
      transition={{ repeat: Infinity, duration: 4 }}
      className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#1c1c1e] to-black flex items-center justify-center border border-white/5 overflow-hidden shadow-2xl"
    >
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="6" y="4" width="12" height="16" rx="2.5" stroke="#ffff00" strokeWidth="1.5"/>
        <path d="M10.5 9.5L14.5 12L10.5 14.5V9.5Z" fill="#ffff00"/>
        <motion.circle 
          cx="12" cy="12" r="10" 
          stroke="url(#logo-grad)" 
          strokeWidth="0.5" 
          strokeDasharray="2 4"
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 20, ease: "linear" }}
        />
        <defs>
          <linearGradient id="logo-grad" x1="0" y1="0" x2="24" y2="24" gradientUnits="userSpaceOnUse">
            <stop stopColor="#ffff00" stopOpacity="0.8"/>
            <stop offset="1" stopColor="#ffff00" stopOpacity="0"/>
          </linearGradient>
        </defs>
      </svg>
    </motion.div>
  </div>
);

// Types
interface Clip {
  id: number;
  title: string;
  start_time: string;
  end_time: string;
  caption?: string;
  style?: string;
  bgm_mood?: string;
  status?: 'pending' | 'processing' | 'completed' | 'failed';
  progress?: number;
}

interface Job {
  id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  video_url: string;
  clips: Clip[];
  error?: string;
}

const App: React.FC = () => {
  const [isInitializing, setIsInitializing] = useState(true);
  const [initProgress, setInitProgress] = useState("Checking factory status...");
  const [updateStatus, setUpdateStatus] = useState<'idle' | 'downloading' | 'ready'>('idle');
  
  const [isBatchMode, setIsBatchMode] = useState(false);
  const [url, setUrl] = useState('');
  const [batchUrls, setBatchUrls] = useState('');
  const [style, setStyle] = useState('hormozi');
  const [jobs, setJobs] = useState<Record<string, Job>>({});
  const [isSettingsOpen, setIsSettingsModalOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<'llm' | 'social'>('llm');
  const [statusMsg, setStatusMsg] = useState('');
  const [isOrchestrating, setIsOrchestrating] = useState(false);
  const [activePreviewVideo, setActivePreviewVideo] = useState<{
    videoUrl: string;
    title: string;
    caption: string;
    style: string;
    start: string;
    end: string;
    bgmMood?: string;
  } | null>(null);
  const [activeFullRepurposeJob, setActiveFullRepurposeJob] = useState<{ job_id: string; video_url: string } | null>(null);

  // Universal AI Config
  const [provider, setProvider] = useState(localStorage.getItem('ai_provider') || 'gemini');
  const [selectedModel, setSelectedModel] = useState(localStorage.getItem('ai_model') || '');
  const [autoRepurpose, setAutoRepurpose] = useState(localStorage.getItem('auto_repurpose') === 'true');
  const [twitterProvider, setTwitterProvider] = useState(localStorage.getItem('repurpose_twitter_provider') || 'gemini');
  const [twitterModel, setTwitterModel] = useState(localStorage.getItem('repurpose_twitter_model') || '');
  const [mediumProvider, setMediumProvider] = useState(localStorage.getItem('repurpose_medium_provider') || 'gemini');
  const [mediumModel, setMediumModel] = useState(localStorage.getItem('repurpose_medium_model') || '');
  const [allModels, setAllModels] = useState<Record<string, string[]>>(
    JSON.parse(localStorage.getItem('ai_models_cache') || '{}')
  );

  // API Keys / Tokens (from localStorage)
  const [keys, setKeys] = useState<Record<string, string>>({
    gemini: localStorage.getItem('key_gemini') || '',
    openai: localStorage.getItem('key_openai') || '',
    anthropic: localStorage.getItem('key_anthropic') || '',
    openrouter: localStorage.getItem('key_openrouter') || '',
    ollama_url: localStorage.getItem('key_ollama_url') || 'http://localhost:11434/v1',
    lm_studio_url: localStorage.getItem('key_lm_studio_url') || 'http://localhost:1234/v1',
    pexels: localStorage.getItem('pexels_api_key') || '',
  });

  const [social, setSocial] = useState<Record<string, string>>({
    ig_token: localStorage.getItem('ig_access_token') || '',
    ig_user: localStorage.getItem('ig_user_id') || '',
    fb_token: localStorage.getItem('fb_access_token') || '',  // Fix #1: separate FB token
    fb_page: localStorage.getItem('fb_page_id') || '',
    ngrok: localStorage.getItem('ngrok_token') || '',
  });

  // Publish Targets
  const [pubYT, setPubYT] = useState(false);
  const [pubIG, setPubIG] = useState(false);
  const [pubFB, setPubFB] = useState(false);
  const [pubTT, setPubTT] = useState(false);

  useEffect(() => {
    let unlistenFn: (() => void) | null = null;
    const startup = async () => {
      const isTauri = (window as any).__TAURI_INTERNALS__ !== undefined;
      if (!isTauri) {
        setIsInitializing(false);
        return;
      }

      // Check for Updates
      try {
        const update = await check();
        if (update?.available) {
          setUpdateStatus('downloading');
          await update.downloadAndInstall();
          setUpdateStatus('ready');
        }
      } catch (err) {
        console.error("Update check failed", err);
      }

      const unlisten = await listen("setup-progress", (event: { payload: string }) => {
        setInitProgress(event.payload);
      });
      unlistenFn = unlisten;
      try {
        const isReady = await invoke("check_factory_status");
        if (!isReady) await invoke("initialize_factory");
        await invoke("start_factory_server");
        let retries = 0;
        while (retries < 10) {
          try { await axios.get(`${API_BASE}/jobs`); break; } 
          catch (e) { await new Promise(r => setTimeout(r, 1000)); retries++; }
        }
        setIsInitializing(false);
      } catch (err: any) { setInitProgress(`Factory Fault: ${err}`); }
    };
    startup();
    return () => {
      if (unlistenFn) unlistenFn();
    };
  }, []);

  useEffect(() => {
    if (isInitializing) return;
    // Fix #8: Only poll actively when there are queued/processing jobs.
    // Use a shorter interval while work is in progress, longer when idle.
    const hasActiveJobs = Object.values(jobs).some(
      j => j.status === 'queued' || j.status === 'processing'
    );
    const interval = hasActiveJobs ? 3000 : 10000;
    const poll = setInterval(async () => {
      try {
        const res = await axios.get(`${API_BASE}/jobs`);
        setJobs(res.data);
      } catch (e) { console.error("Polling failed"); }
    }, interval);
    return () => clearInterval(poll);
  }, [isInitializing, jobs]);

  const saveConfig = () => {
    localStorage.setItem('ai_provider', provider);
    localStorage.setItem('ai_model', selectedModel);
    localStorage.setItem('ai_models_cache', JSON.stringify(allModels));
    
    // Repurposing configurations
    localStorage.setItem('auto_repurpose', String(autoRepurpose));
    localStorage.setItem('repurpose_twitter_provider', twitterProvider);
    localStorage.setItem('repurpose_twitter_model', twitterModel);
    localStorage.setItem('repurpose_medium_provider', mediumProvider);
    localStorage.setItem('repurpose_medium_model', mediumModel);
    
    Object.entries(keys).forEach(([k, v]) => localStorage.setItem(`key_${k}`, v));
    localStorage.setItem('pexels_api_key', keys.pexels);
    
    localStorage.setItem('ig_access_token', social.ig_token);
    localStorage.setItem('ig_user_id', social.ig_user);
    localStorage.setItem('fb_access_token', social.fb_token);  // Fix #1: save FB token separately
    localStorage.setItem('fb_page_id', social.fb_page);
    localStorage.setItem('ngrok_token', social.ngrok);
    
    setIsSettingsModalOpen(false);
  };

  const fetchModels = async (targetProvider: string) => {
    setStatusMsg(`Syncing model catalog for ${targetProvider}...`);
    try {
      const res = await axios.post(`${API_BASE}/models/fetch`, {
        provider: targetProvider,
        api_key: keys[targetProvider] || '',
        base_url: keys[`${targetProvider}_url`] || null
      });
      const models = res.data;
      const newCache = { ...allModels, [targetProvider]: models };
      setAllModels(newCache);
      localStorage.setItem('ai_models_cache', JSON.stringify(newCache));
      if (provider === targetProvider && models.length > 0) setSelectedModel(models[0]);
      setStatusMsg(`${models.length} models synced successfully.`);
    } catch (err: any) {
      alert(`Failed to fetch models: ${err.response?.data?.detail || err.message}`);
    }
  };

  const handleTiktokLogin = async () => {
    await axios.get(`${API_BASE}/tiktok/login`);
    alert("Login window opened. Please log in manually and then close that window.");
  };

  const orchestrate = async () => {
    const activeKey = keys[provider] || keys[`${provider}_url`];
    if (!activeKey && !['ollama', 'lm_studio'].includes(provider)) return alert(`Please set your ${provider} API Key in Settings.`);
    
    let urls = isBatchMode 
      ? batchUrls.split('\n').map(u => u.trim()).filter(u => u !== '')
      : [url.trim()].filter(u => u !== '');

    if (urls.length === 0) return alert("Enter at least one YouTube URL.");
    if (!selectedModel) return alert("Please select an AI model from the dropdown.");

    setIsOrchestrating(true);
    
    for (let i = 0; i < urls.length; i++) {
      const currentUrl = urls[i];
      setStatusMsg(`Orchestrating [${i+1}/${urls.length}]: ${currentUrl}...`);

      try {
        const prompt = `You are a viral content strategist. Analyze this YouTube video URL: ${currentUrl}. 
        Identify as many highly viral segments as possible (MINIMUM 4 clips, let the content dictate the maximum). Each clip should be 15-45 seconds long and have a strong hook.
        
        Output a JSON object following this schema strictly:
        {
            "video_url": "${currentUrl}",
            "clips": [
                {
                    "id": number (unique timestamp integer),
                    "title": "Short_Descriptive_Title",
                    "start_time": "HH:MM:SS",
                    "end_time": "HH:MM:SS",
                    "caption": "Catchy social media caption with emojis 🚀✨",
                    "style": "${style}",
                    "bgm_mood": "lofi"|"epic"|"funny"|"tense"|"upbeat",
                    "broll_keywords": ["keyword1", "keyword2"],
                    "timeline": [
                        { "rel_start": number, "rel_end": number, "crop_mode": "center"|"left"|"right"|"track", "zoom": number }
                    ]
                }
            ]
        }
        
        CRITICAL INSTRUCTIONS:
        1. "crop_mode": You MUST use "track" if there is a person speaking on screen so the AI camera follows them. Only use "center/left/right" for static, non-human shots.
        2. "broll_keywords": You MUST provide 1-2 generic, highly relevant stock footage keywords (e.g., "coding", "business meeting", "angry") for the engine to fetch and overlay.
        3. "timeline": Break the clip down into 1-2 sub-segments if the camera angle or speaker changes.
        Focus on high-energy parts or key insights. Ensure HH:MM:SS format.`;

        const orchRes = await axios.post(`${API_BASE}/orchestrate`, {
          provider,
          model: selectedModel,
          api_key: keys[provider] || 'local',
          base_url: keys[`${provider}_url`] || null,
          prompt
        });

        const orchestration = orchRes.data;
        orchestration.pexels_key = keys.pexels;
        orchestration.publish_targets = [];
        if (pubYT) orchestration.publish_targets.push('youtube');
        if (pubIG) orchestration.publish_targets.push('instagram');
        if (pubFB) orchestration.publish_targets.push('facebook');
        if (pubTT) orchestration.publish_targets.push('tiktok');
        
        orchestration.ig_access_token = social.ig_token;
        orchestration.ig_user_id = social.ig_user;
        // Fix #1: Use dedicated FB token; fall back to shared Meta token if FB token is blank.
        orchestration.fb_access_token = social.fb_token || social.ig_token;
        orchestration.fb_page_id = social.fb_page;
        orchestration.ngrok_token = social.ngrok;
        
        // Content Repurposing Configs
        orchestration.auto_repurpose = autoRepurpose;
        orchestration.twitter_provider = twitterProvider;
        orchestration.twitter_model = twitterModel;
        orchestration.twitter_key = keys[twitterProvider] || 'local';
        orchestration.twitter_base_url = keys[`${twitterProvider}_url`] || null;
        orchestration.medium_provider = mediumProvider;
        orchestration.medium_model = mediumModel;
        orchestration.medium_key = keys[mediumProvider] || 'local';
        orchestration.medium_base_url = keys[`${mediumProvider}_url`] || null;

        await axios.post(`${API_BASE}/process`, orchestration);
        
      } catch (err: any) {
        console.error(err);
        setStatusMsg(`Error: ${err.response?.data?.detail || err.message}`);
      }
    }

    setStatusMsg("All items dispatched to the factory floor.");
    setIsOrchestrating(false);
  };

  return (
    <div className="flex h-screen w-full bg-background overflow-hidden selection:bg-primary selection:text-black font-sans text-[#e1e1e6]">
      <AnimatePresence>
        {isInitializing && (
          <motion.div initial={{ opacity: 1 }} exit={{ opacity: 0, y: -20 }} className="fixed inset-0 z-[100] bg-background flex flex-col items-center justify-center p-12 text-center">
             <Logo />
             <h2 className="mt-8 text-4xl font-black tracking-tight text-white italic lowercase font-love text-white">fypd</h2>
             <div className="mt-12 w-64 h-1 bg-white/5 rounded-full overflow-hidden relative">
                <motion.div animate={{ x: [-256, 256] }} transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }} className="w-full h-full bg-primary shadow-[0_0_15px_rgba(255,255,0,0.5)]" />
             </div>
             <p className="mt-6 text-[10px] uppercase font-black tracking-[0.3em] text-primary animate-pulse">{initProgress}</p>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {updateStatus !== 'idle' && (
          <motion.div 
            initial={{ opacity: 0, x: 50 }} 
            animate={{ opacity: 1, x: 0 }} 
            exit={{ opacity: 0, x: 50 }} 
            className="fixed top-8 right-8 z-[200] glass p-4 rounded-3xl border border-white/10 shadow-[0_20px_40px_rgba(0,0,0,0.8)] flex items-center gap-4 bg-[#0a0a0c]/80 backdrop-blur-2xl"
          >
            {updateStatus === 'downloading' ? (
              <>
                <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: "linear" }}>
                  <RefreshCw className="w-4 h-4 text-primary" />
                </motion.div>
                <span className="text-[10px] font-black text-white tracking-widest uppercase">Downloading Update...</span>
              </>
            ) : (
              <>
                <Check className="w-4 h-4 text-green-400" />
                <span className="text-[10px] font-black text-white tracking-widest uppercase">Update Ready</span>
                <button 
                  onClick={() => relaunch()} 
                  className="bg-primary text-black px-4 py-2.5 rounded-xl text-[9px] font-black uppercase hover:scale-[1.03] transition-all ml-2"
                >
                  Restart
                </button>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Sidebar / Control Center */}
      <motion.aside initial={{ x: -300, opacity: 0 }} animate={{ x: 0, opacity: 1 }} className="w-96 glass border-r border-white/5 flex flex-col p-8 z-20 overflow-y-auto">
        <div className="flex items-center gap-3 mb-12">
          <Logo />
          <div>
            <h1 className="text-4xl font-normal tracking-tight text-white italic font-love lowercase leading-none">fypd</h1>
            <p className="text-[10px] uppercase tracking-widest text-primary font-bold mt-1">Autonomous Content Factory</p>
          </div>
        </div>

        <div className="space-y-8 flex-1">
          {/* AI Orchestrator Selector */}
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-[10px] font-black text-text-dim uppercase tracking-[0.2em] flex items-center gap-2">
                <Cpu className="w-3 h-3 text-primary" /> AI Intelligence
              </label>
              <select value={provider} onChange={(e) => {setProvider(e.target.value); setSelectedModel(allModels[e.target.value]?.[0] || '');}} className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none appearance-none cursor-pointer hover:bg-white/10 transition-colors text-white">
                <option value="gemini" className="bg-[#1c1c1e]">Google Gemini</option>
                <option value="openai" className="bg-[#1c1c1e]">OpenAI</option>
                <option value="anthropic" className="bg-[#1c1c1e]">Anthropic Claude</option>
                <option value="openrouter" className="bg-[#1c1c1e]">OpenRouter</option>
                <option value="ollama" className="bg-[#1c1c1e]">Ollama (Local)</option>
                <option value="lm_studio" className="bg-[#1c1c1e]">LM Studio (Local)</option>
              </select>
            </div>
            
            <div className="space-y-2">
              <label className="text-[10px] font-black text-text-dim uppercase tracking-[0.2em] flex items-center gap-2">
                <Zap className="w-3 h-3 text-primary" /> Active Model
              </label>
              <select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)} className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none appearance-none cursor-pointer hover:bg-white/10 transition-colors text-white disabled:opacity-30" disabled={!allModels[provider]}>
                {allModels[provider]?.map(m => <option key={m} value={m} className="bg-[#1c1c1e]">{m}</option>) || <option>No models found</option>}
              </select>
            </div>
          </div>

          <div className="h-px bg-white/5" />

          {/* Mode Toggle */}
          <div className="flex bg-white/5 p-1 rounded-lg border border-white/5">
            <button onClick={() => setIsBatchMode(false)} className={`flex-1 py-2 px-3 rounded-md text-sm font-medium transition-all ${!isBatchMode ? 'bg-white/10 text-white shadow-lg' : 'text-text-dim hover:text-white'}`}>Single</button>
            <button onClick={() => setIsBatchMode(true)} className={`flex-1 py-2 px-3 rounded-md text-sm font-medium transition-all ${isBatchMode ? 'bg-white/10 text-white shadow-lg' : 'text-text-dim hover:text-white'}`}>Batch</button>
          </div>

          {/* URL Input */}
          <div className="space-y-2">
            <label className="text-[10px] font-black text-text-dim uppercase tracking-[0.2em] flex items-center gap-2">
              <Globe className="w-3 h-3 text-primary" /> YouTube Ingestion
            </label>
            {!isBatchMode ? (
              <input type="text" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Paste YouTube URL..." className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-primary/50 transition-colors text-white placeholder:text-white/20" />
            ) : (
              <textarea value={batchUrls} onChange={(e) => setBatchUrls(e.target.value)} placeholder="Paste URLs (one per line)..." className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm h-32 focus:outline-none focus:border-primary/50 transition-colors resize-none text-white placeholder:text-white/20" />
            )}
          </div>

          {/* Style & Auto-Pub */}
          <div className="space-y-4 pt-4 border-t border-white/5">
            <div className="space-y-2">
              <label className="text-[10px] font-black text-text-dim uppercase tracking-[0.2em] flex items-center gap-2">
                <Video className="w-3 h-3 text-primary" /> Visual Style
              </label>
              <select value={style} onChange={(e) => setStyle(e.target.value)} className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none appearance-none cursor-pointer hover:bg-white/10 transition-colors text-white">
                <option value="hormozi" className="bg-[#1c1c1e]">Hormozi (High Impact)</option>
                <option value="minimalist" className="bg-[#1c1c1e]">Minimalist (Clean)</option>
                <option value="neon" className="bg-[#1c1c1e]">Neon (Glow)</option>
              </select>
            </div>

            <div className="space-y-2">
              <label className="text-[10px] font-black text-text-dim uppercase tracking-[0.2em] flex items-center gap-2">
                <Smartphone className="w-3 h-3 text-primary" /> Auto-Distribution
              </label>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { id: 'yt', active: pubYT, set: setPubYT, label: 'Shorts' },
                  { id: 'ig', active: pubIG, set: setPubIG, label: 'Reels' },
                  { id: 'fb', active: pubFB, set: setPubFB, label: 'Facebook' },
                  { id: 'tt', active: pubTT, set: setPubTT, label: 'TikTok' },
                ].map(p => (
                  <button key={p.id} onClick={() => p.set(!p.active)} className={`flex items-center justify-center p-3 rounded-xl border text-[10px] font-black uppercase tracking-widest transition-all ${p.active ? 'bg-primary text-black border-primary shadow-[0_0_15px_rgba(255,255,0,0.1)]' : 'bg-white/5 border-transparent text-text-dim hover:border-white/10 hover:text-white'}`}>{p.label}</button>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="mt-8 space-y-3">
          <button onClick={orchestrate} disabled={isOrchestrating} className="w-full bg-primary text-black py-4 rounded-2xl font-black uppercase tracking-widest text-xs flex items-center justify-center gap-3 hover:scale-[1.02] active:scale-[0.98] transition-all shadow-[0_10px_30px_rgba(255,255,0,0.1)] disabled:opacity-50 disabled:scale-100 disabled:shadow-none">
            {isOrchestrating ? <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: "linear" }}><RefreshCw className="w-5 h-5" /></motion.div> : <Play className="fill-current w-4 h-4" />}
            Orchestrate
          </button>
          <button onClick={() => setIsSettingsModalOpen(true)} className="w-full bg-white/5 text-white/40 py-3 rounded-2xl font-black uppercase tracking-widest text-[9px] flex items-center justify-center gap-2 hover:bg-white/10 hover:text-white transition-all border border-transparent hover:border-white/5">
            <Settings className="w-3 h-3" /> System Configuration
          </button>
        </div>

        {statusMsg && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mt-6 p-4 rounded-xl bg-white/5 border border-white/5">
             <p className="text-[10px] text-center text-primary font-bold uppercase tracking-wider">{statusMsg}</p>
          </motion.div>
        )}
      </motion.aside>

      {/* Main Content / Factory Floor */}
      <main className="flex-1 p-12 overflow-y-auto relative bg-[#050505]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,0,0.03),transparent_40%)] pointer-events-none" />
        <header className="mb-16 flex justify-between items-end">
          <div>
            <div className="flex items-center gap-4 mb-2">
               <h2 className="text-5xl font-black tracking-tight text-white uppercase italic italic">Factory Floor</h2>
               <div className="h-1 flex-1 w-32 bg-primary/20 rounded-full hidden md:block" />
            </div>
            <p className="text-text-dim text-xl font-medium tracking-tight">The autonomous pipeline for high-retention viral growth.</p>
          </div>
          <div className="flex gap-12 border-l border-white/5 pl-12">
            <div>
              <p className="text-[10px] uppercase font-black text-text-dim tracking-[0.2em] mb-1">Active Cycles</p>
              <p className="text-3xl font-black text-white tabular-nums">{Object.values(jobs).filter(j => j.status !== 'completed' && j.status !== 'failed').length}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase font-black text-text-dim tracking-[0.2em] mb-1">Produced</p>
              <p className="text-3xl font-black text-white tabular-nums">{Object.values(jobs).reduce((acc, j) => acc + j.clips.length, 0)}</p>
            </div>
          </div>
        </header>

        {/* Jobs Grouped Layout */}
        <div className="space-y-12">
          <AnimatePresence mode="popLayout">
            {Object.values(jobs).reverse().map((job) => (
              <motion.div 
                key={job.id} 
                layout 
                initial={{ opacity: 0, y: 20 }} 
                animate={{ opacity: 1, y: 0 }} 
                exit={{ opacity: 0, scale: 0.95 }}
                className="glass p-8 rounded-[48px] border border-white/5 relative overflow-hidden bg-white/[0.02]"
              >
                {/* Background Ambient Glow for active jobs */}
                {job.status === 'processing' && (
                  <div className="absolute top-0 right-0 w-[200px] h-[200px] rounded-full bg-primary/5 blur-[80px] pointer-events-none animate-pulse" />
                )}
                
                {/* Job Panel Header */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8 pb-6 border-b border-white/5">
                  <div className="space-y-2">
                    <span className="text-[9px] font-black tracking-widest text-primary uppercase animate-pulse flex items-center gap-1.5">
                      <Cpu className="w-3.5 h-3.5 text-primary" /> Source Video Intake
                    </span>
                    <h3 className="text-xl font-bold text-white tracking-tight flex items-center gap-2 line-clamp-1">
                      {job.video_url}
                    </h3>
                    <div className="flex items-center gap-3">
                      <span className={`px-2.5 py-1 rounded-lg text-[8px] font-black uppercase tracking-[0.2em] backdrop-blur-md border ${job.status === 'completed' ? 'bg-green-500/10 border-green-500/30 text-green-400' : job.status === 'failed' ? 'bg-red-500/10 border-red-500/30 text-red-400' : 'bg-primary/10 border-primary/30 text-primary animate-pulse'}`}>
                        {job.status}
                      </span>
                      <span className="text-[9px] text-text-dim uppercase tracking-wider font-bold">
                        {job.clips.length} Short Clips Curated
                      </span>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-4">
                    <button 
                      onClick={() => setActiveFullRepurposeJob({ job_id: job.id, video_url: job.video_url })}
                      className="bg-primary/5 border border-primary/20 hover:border-primary text-primary hover:bg-primary hover:text-black px-6 py-3.5 rounded-2xl text-[9px] font-black uppercase tracking-widest transition-all flex items-center gap-2 cursor-pointer shadow-lg shadow-primary/5 active:scale-95"
                    >
                      <Sparkles className="w-3.5 h-3.5" /> Repurpose Full Video
                    </button>
                  </div>
                </div>

                {/* Inner Clips Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-8">
                  {job.clips.map((clip) => (
                    <JobCard 
                      key={clip.id} 
                      job={job} 
                      clip={clip} 
                      onOpenCinema={(url, title, caption, style, start, end, bgmMood) => 
                        setActivePreviewVideo({ videoUrl: url, title, caption, style, start: start, end: end, bgmMood })
                      } 
                    />
                  ))}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>

        {Object.keys(jobs).length === 0 && (
          <div className="h-[60vh] flex flex-col items-center justify-center text-center">
            <motion.div animate={{ rotate: [0, 90, 180, 270, 360], opacity: [0.1, 0.2, 0.1] }} transition={{ repeat: Infinity, duration: 10, ease: "linear" }} className="w-32 h-32 rounded-[40px] bg-white/5 flex items-center justify-center mb-8 border border-white/5 shadow-2xl">
              <Cpu className="text-white w-12 h-12" />
            </motion.div>
            <h3 className="text-2xl font-black text-white/10 uppercase tracking-[0.3em]">Awaiting Command</h3>
            <p className="text-white/5 text-sm mt-4 font-bold tracking-widest uppercase">Sync a model and ingest a URL to start production</p>
          </div>
        )}
      </main>

      {/* Settings Modal */}
      <AnimatePresence>
        {isSettingsOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 bg-black/90 backdrop-blur-xl" onClick={() => setIsSettingsModalOpen(false)} />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="w-full max-w-4xl bg-[#121214] border border-white/10 rounded-[48px] p-0 relative z-10 shadow-[0_50px_100px_rgba(0,0,0,0.5)] overflow-hidden flex flex-col max-h-[90vh]">
              
              <div className="flex border-b border-white/5">
                <button onClick={() => setSettingsTab('llm')} className={`flex-1 py-8 text-[10px] font-black uppercase tracking-[0.3em] transition-all flex items-center justify-center gap-3 ${settingsTab === 'llm' ? 'bg-white/5 text-primary border-b-2 border-primary' : 'text-text-dim hover:text-white'}`}>
                  <Key className="w-4 h-4" /> Intelligence Keys
                </button>
                <button onClick={() => setSettingsTab('social')} className={`flex-1 py-8 text-[10px] font-black uppercase tracking-[0.3em] transition-all flex items-center justify-center gap-3 ${settingsTab === 'social' ? 'bg-white/5 text-primary border-b-2 border-primary' : 'text-text-dim hover:text-white'}`}>
                  <Share2 className="w-4 h-4" /> Social Accounts
                </button>
              </div>

              <div className="p-16 overflow-y-auto">
                {settingsTab === 'llm' ? (
                  <div className="space-y-12">
                    <section className="space-y-8">
                       {[
                         { id: 'gemini', name: 'Google Gemini' },
                         { id: 'openai', name: 'OpenAI' },
                         { id: 'anthropic', name: 'Anthropic' },
                         { id: 'openrouter', name: 'OpenRouter' },
                       ].map(p => (
                         <div key={p.id} className="grid grid-cols-1 md:grid-cols-4 gap-6 items-end">
                            <div className="md:col-span-3 space-y-3">
                              <label className="text-[10px] font-bold text-text-dim uppercase tracking-widest">{p.name} API Key</label>
                              <input type="password" value={keys[p.id]} onChange={e => setKeys({...keys, [p.id]: e.target.value})} className="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm focus:outline-none focus:border-primary/40 transition-all text-white" />
                            </div>
                            <button onClick={() => fetchModels(p.id)} className="bg-white/5 border border-white/10 text-white/50 py-4 rounded-2xl text-[9px] font-black uppercase tracking-widest hover:bg-primary hover:text-black transition-all flex items-center justify-center gap-2">
                               <RefreshCw className="w-3 h-3" /> Fetch Models
                            </button>
                         </div>
                       ))}
                       <div className="h-px bg-white/5" />
                       <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                          <div className="space-y-3">
                            <label className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Ollama Endpoint</label>
                            <input value={keys.ollama_url} onChange={e => setKeys({...keys, ollama_url: e.target.value})} className="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm focus:outline-none focus:border-primary/40 transition-all text-white" />
                            <button onClick={() => fetchModels('ollama')} className="text-primary text-[9px] font-black uppercase tracking-widest flex items-center gap-2 mt-2"><RefreshCw className="w-3 h-3" /> Sync Local Models</button>
                          </div>
                          <div className="space-y-3">
                            <label className="text-[10px] font-bold text-text-dim uppercase tracking-widest">LM Studio Endpoint</label>
                            <input value={keys.lm_studio_url} onChange={e => setKeys({...keys, lm_studio_url: e.target.value})} className="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm focus:outline-none focus:border-primary/40 transition-all text-white" />
                            <button onClick={() => fetchModels('lm_studio')} className="text-primary text-[9px] font-black uppercase tracking-widest flex items-center gap-2 mt-2"><RefreshCw className="w-3 h-3" /> Sync Local Models</button>
                          </div>
                       </div>
                    </section>
                    
                    <div className="h-px bg-white/5" />
                    <section className="space-y-6">
                      <div>
                        <h4 className="text-xs font-black text-primary uppercase tracking-[0.25em] mb-1">Content Repurposing Hub</h4>
                        <p className="text-[10px] text-text-dim">Configure custom models for autonomous or on-demand content generation.</p>
                      </div>
                      
                      <div className="flex items-center justify-between bg-white/5 p-6 rounded-3xl border border-white/5">
                        <div>
                          <p className="text-[10px] font-black text-white uppercase tracking-wider">Auto-Generate Repurposed Content</p>
                          <p className="text-[9px] text-text-dim">Generate Twitter threads and Medium articles automatically in the background after clip production.</p>
                        </div>
                        <button 
                          type="button"
                          onClick={() => setAutoRepurpose(!autoRepurpose)}
                          className={`w-12 h-6 rounded-full p-1 transition-all flex items-center ${autoRepurpose ? 'bg-primary justify-end' : 'bg-white/10 justify-start'}`}
                        >
                          <motion.div 
                            layout
                            className="w-4 h-4 rounded-full bg-black"
                          />
                        </button>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 pt-4">
                        {/* Twitter Repurposing */}
                        <div className="space-y-4 bg-white/5 p-6 rounded-3xl border border-white/5">
                          <p className="text-[10px] font-black text-white uppercase tracking-widest">Twitter Copywriter Model</p>
                          
                          <div className="space-y-2">
                            <label className="text-[9px] font-bold text-text-dim uppercase tracking-wider">Provider</label>
                            <select 
                              value={twitterProvider} 
                              onChange={(e) => {
                                setTwitterProvider(e.target.value);
                                setTwitterModel(allModels[e.target.value]?.[0] || '');
                              }} 
                              className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-xs focus:outline-none text-white cursor-pointer"
                            >
                              <option value="gemini" className="bg-[#1c1c1e]">Google Gemini</option>
                              <option value="openai" className="bg-[#1c1c1e]">OpenAI</option>
                              <option value="anthropic" className="bg-[#1c1c1e]">Anthropic Claude</option>
                              <option value="openrouter" className="bg-[#1c1c1e]">OpenRouter</option>
                              <option value="ollama" className="bg-[#1c1c1e]">Ollama (Local)</option>
                              <option value="lm_studio" className="bg-[#1c1c1e]">LM Studio (Local)</option>
                            </select>
                          </div>

                          <div className="space-y-2">
                            <label className="text-[9px] font-bold text-text-dim uppercase tracking-wider">Active Model</label>
                            <select 
                              value={twitterModel} 
                              onChange={(e) => setTwitterModel(e.target.value)} 
                              className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-xs focus:outline-none text-white cursor-pointer disabled:opacity-30"
                              disabled={!allModels[twitterProvider]}
                            >
                              {allModels[twitterProvider]?.map(m => (
                                <option key={m} value={m} className="bg-[#1c1c1e]">{m}</option>
                              )) || <option className="bg-[#1c1c1e]">No models found</option>}
                            </select>
                          </div>
                        </div>

                        {/* Medium Repurposing */}
                        <div className="space-y-4 bg-white/5 p-6 rounded-3xl border border-white/5">
                          <p className="text-[10px] font-black text-white uppercase tracking-widest">Medium Editorial Model</p>
                          
                          <div className="space-y-2">
                            <label className="text-[9px] font-bold text-text-dim uppercase tracking-wider">Provider</label>
                            <select 
                              value={mediumProvider} 
                              onChange={(e) => {
                                setMediumProvider(e.target.value);
                                setMediumModel(allModels[e.target.value]?.[0] || '');
                              }} 
                              className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-xs focus:outline-none text-white cursor-pointer"
                            >
                              <option value="gemini" className="bg-[#1c1c1e]">Google Gemini</option>
                              <option value="openai" className="bg-[#1c1c1e]">OpenAI</option>
                              <option value="anthropic" className="bg-[#1c1c1e]">Anthropic Claude</option>
                              <option value="openrouter" className="bg-[#1c1c1e]">OpenRouter</option>
                              <option value="ollama" className="bg-[#1c1c1e]">Ollama (Local)</option>
                              <option value="lm_studio" className="bg-[#1c1c1e]">LM Studio (Local)</option>
                            </select>
                          </div>

                          <div className="space-y-2">
                            <label className="text-[9px] font-bold text-text-dim uppercase tracking-wider">Active Model</label>
                            <select 
                              value={mediumModel} 
                              onChange={(e) => setMediumModel(e.target.value)} 
                              className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-xs focus:outline-none text-white cursor-pointer disabled:opacity-30"
                              disabled={!allModels[mediumProvider]}
                            >
                              {allModels[mediumProvider]?.map(m => (
                                <option key={m} value={m} className="bg-[#1c1c1e]">{m}</option>
                              )) || <option className="bg-[#1c1c1e]">No models found</option>}
                            </select>
                          </div>
                        </div>
                      </div>
                    </section>
                  </div>
                ) : (
                  <div className="space-y-12">
                    <section className="space-y-6">
                       <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                          <div className="space-y-3 col-span-2">
                            <label className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Meta Long-Lived Token</label>
                            <input type="password" value={social.ig_token} onChange={e => setSocial({...social, ig_token: e.target.value})} className="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm focus:outline-none focus:border-primary/40 transition-all text-white" />
                          </div>
                          <div className="space-y-3">
                            <label className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Instagram ID</label>
                            <input value={social.ig_user} onChange={e => setSocial({...social, ig_user: e.target.value})} className="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm focus:outline-none" />
                          </div>
                          <div className="space-y-3">
                            <label className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Facebook Page ID</label>
                            <input value={social.fb_page} onChange={e => setSocial({...social, fb_page: e.target.value})} className="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm focus:outline-none" />
                          </div>
                          {/* Fix #1: Dedicated FB token field */}
                          <div className="space-y-3 col-span-2">
                            <label className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Facebook Long-Lived Token</label>
                            <input type="password" value={social.fb_token} onChange={e => setSocial({...social, fb_token: e.target.value})} className="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm focus:outline-none focus:border-primary/40 transition-all text-white" placeholder="Leave blank to share Meta token above" />
                            <p className="text-[9px] text-text-dim">Optional — if blank, the Meta Long-Lived Token above is used for both IG and FB.</p>
                          </div>
                          <div className="space-y-3 col-span-2 pt-4">
                            <label className="text-[10px] font-bold text-text-dim uppercase tracking-widest flex items-center gap-2"><Server className="w-3 h-3" /> Ngrok Tunnel Token</label>
                            <input type="password" value={social.ngrok} onChange={e => setSocial({...social, ngrok: e.target.value})} className="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm focus:outline-none" />
                          </div>
                       </div>
                    </section>
                    <section className="bg-white/5 p-8 rounded-3xl border border-white/10 flex items-center justify-between">
                      <div>
                        <p className="font-black text-white text-lg tracking-tight uppercase italic italic">TikTok Protocol</p>
                        <p className="text-xs text-text-dim font-medium">Session persists in local browser cache</p>
                      </div>
                      <button onClick={handleTiktokLogin} className="bg-white text-black px-8 py-3 rounded-xl text-xs font-black uppercase tracking-widest hover:scale-105 transition-all">Login</button>
                    </section>
                  </div>
                )}
              </div>

              <div className="p-12 pt-0 flex gap-4">
                <button onClick={() => setIsSettingsModalOpen(false)} className="flex-1 bg-white/5 text-white/50 py-5 rounded-[20px] font-black uppercase tracking-[0.2em] text-[10px] hover:bg-white/10 border border-white/5 transition-all">Discard</button>
                <button onClick={saveConfig} className="flex-1 bg-primary text-black py-5 rounded-[20px] font-black uppercase tracking-[0.2em] text-[10px] hover:scale-[1.02] shadow-xl shadow-primary/10 transition-all">Commit Configuration</button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {activePreviewVideo && (
          <CinemaPlayerModal 
            video={activePreviewVideo} 
            onClose={() => setActivePreviewVideo(null)} 
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {activeFullRepurposeJob && (
          <FullVideoRepurposeModal 
            job={activeFullRepurposeJob}
            onClose={() => setActiveFullRepurposeJob(null)}
            twitterProvider={twitterProvider}
            twitterModel={twitterModel}
            mediumProvider={mediumProvider}
            mediumModel={mediumModel}
            keys={keys}
          />
        )}
      </AnimatePresence>
    </div>
  );
};

const ProcessingPhaseTracker: React.FC<{ elapsedSeconds: number, progress?: number }> = ({ elapsedSeconds, progress }) => {
  const phases = [
    { name: "Ingesting Media", desc: "yt-dlp establishing selective byte-range download...", minTime: 0 },
    { name: "Scene Cut Detection", desc: "PySceneDetect identifying hard visual scene changes...", minTime: 6 },
    { name: "Neural Speaker Tracking", desc: "MediaPipe calculating active speaker coordinates...", minTime: 14 },
    { name: "Kinetic Text Render", desc: "MoviePy rendering animated retention typography...", minTime: 23 },
    { name: "Audio Ducking & Mastering", desc: "Mixing dialogue with ducked background music layers...", minTime: 32 },
    { name: "Final Video Compile", desc: "Compiling master 9:16 vertical H.264 file...", minTime: 40 }
  ];
  
  // If we have real progress from the backend, use it to determine the active phase
  let activeIdx = phases.length - 1;
  if (progress !== undefined) {
      activeIdx = Math.min(Math.floor((progress / 100) * phases.length), phases.length - 1);
  } else {
      for (let i = 0; i < phases.length; i++) {
        if (elapsedSeconds < phases[i].minTime) {
          activeIdx = i - 1;
          break;
        }
      }
  }
  if (activeIdx < 0) activeIdx = 0;
  
  return (
    <div className="w-full text-left space-y-3.5 bg-black/45 p-5.5 rounded-[28px] border border-white/5 shadow-inner">
      <div className="flex items-center justify-between">
        <span className="text-[9px] font-black tracking-widest text-primary uppercase animate-pulse flex items-center gap-1.5">
          <motion.span animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1.5 }} className="w-1.5 h-1.5 rounded-full bg-primary" />
          Autonomous Pipeline
        </span>
        <span className="text-[9px] font-black tracking-widest text-white/30 tabular-nums">{elapsedSeconds}s</span>
      </div>

      <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden relative">
        <motion.div 
          initial={{ width: 0 }} 
          animate={{ width: `${progress !== undefined ? progress : Math.min(elapsedSeconds * (100 / 120), 98)}%` }} 
          className="absolute h-full bg-primary shadow-[0_0_15px_rgba(255,255,0,0.5)] transition-all duration-500" 
        />
      </div>

      <div className="space-y-2.5 pt-1">
        {phases.map((p, idx) => {
          const isDone = idx < activeIdx;
          const isActive = idx === activeIdx;
          return (
            <div key={p.name} className="flex gap-2.5 items-start">
              <div className="mt-0.5 flex-shrink-0">
                {isDone ? (
                  <div className="w-3 h-3 rounded-full bg-green-500 flex items-center justify-center text-[7px] font-black text-black">✓</div>
                ) : isActive ? (
                  <div className="w-3 h-3 rounded-full border border-primary flex items-center justify-center relative">
                    <motion.div animate={{ scale: [0.5, 1, 0.5] }} transition={{ repeat: Infinity, duration: 1.2 }} className="w-1 h-1 rounded-full bg-primary" />
                  </div>
                ) : (
                  <div className="w-3 h-3 rounded-full border border-white/10" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-[8.5px] font-bold uppercase tracking-wider ${isActive ? 'text-white font-black' : isDone ? 'text-white/45' : 'text-white/20'}`}>{p.name}</p>
                {isActive && <p className="text-[7.5px] text-text-dim mt-0.5 leading-tight font-medium">{p.desc}</p>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

interface FullVideoRepurposeModalProps {
  job: {
    job_id: string;
    video_url: string;
  } | null;
  onClose: () => void;
  twitterProvider: string;
  twitterModel: string;
  mediumProvider: string;
  mediumModel: string;
  keys: Record<string, string>;
}

const FullVideoRepurposeModal: React.FC<FullVideoRepurposeModalProps> = ({ 
  job, 
  onClose,
  twitterProvider,
  twitterModel,
  mediumProvider,
  mediumModel,
  keys
}) => {
  const [tab, setTab] = useState<'tweets' | 'medium'>('tweets');
  const [tweets, setTweets] = useState<string[]>([]);
  const [article, setArticle] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingMsg, setProcessingMsg] = useState('');
  const [error, setError] = useState('');
  const [directive, setDirective] = useState('');
  const [isCopied, setIsCopied] = useState(false);

  useEffect(() => {
    if (job) {
      loadCachedData();
    }
  }, [job]);

  const loadCachedData = async () => {
    if (!job) return;
    setIsLoading(true);
    setError('');
    try {
      const tweetsUrl = `${API_BASE}/videos/Job_${job.job_id}_full_tweets.json`;
      const mediumUrl = `${API_BASE}/videos/Job_${job.job_id}_full_medium.md`;

      const [tweetsRes, mediumRes] = await Promise.allSettled([
        axios.get(tweetsUrl),
        axios.get(mediumUrl)
      ]);

      if (tweetsRes.status === 'fulfilled') {
        setTweets(tweetsRes.value.data.tweets || []);
      } else {
        setTweets([]);
      }

      if (mediumRes.status === 'fulfilled') {
        setArticle(mediumRes.value.data);
      } else {
        setArticle('');
      }

      setIsLoading(false);
    } catch (e) {
      console.error("Cache load failed", e);
      setIsLoading(false);
    }
  };

  const handleRepurpose = async (customDirective: string = '') => {
    if (!job) return;
    
    const tKey = keys[twitterProvider] || keys[`${twitterProvider}_url`];
    const mKey = keys[mediumProvider] || keys[`${mediumProvider}_url`];
    
    if (!tKey && !['ollama', 'lm_studio'].includes(twitterProvider)) {
      return alert(`Please set your ${twitterProvider} API Key in Settings for Twitter copywriting.`);
    }
    if (!mKey && !['ollama', 'lm_studio'].includes(mediumProvider)) {
      return alert(`Please set your ${mediumProvider} API Key in Settings for Medium article writing.`);
    }

    setIsProcessing(true);
    setError('');
    
    const stages = [
      "Harvesting YouTube subtitle streams...",
      "Analyzing long-form video narrative and metadata...",
      "Splicing text transcripts into structural segments...",
      "Orchestrating Twitter model for hooks & thread structure...",
      "Refining Medium model for headings and blogging flow...",
      "Finalizing copywriting syntax..."
    ];
    
    let stageIdx = 0;
    setProcessingMsg(stages[0]);
    const stageInterval = setInterval(() => {
      stageIdx++;
      if (stageIdx < stages.length) {
        setProcessingMsg(stages[stageIdx]);
      }
    }, 2500);

    try {
      const res = await axios.post(`${API_BASE}/repurpose/full`, {
        job_id: job.job_id,
        video_url: job.video_url,
        
        twitter_provider: twitterProvider,
        twitter_model: twitterModel,
        twitter_key: keys[twitterProvider] || 'local',
        twitter_base_url: keys[`${twitterProvider}_url`] || null,
        
        medium_provider: mediumProvider,
        medium_model: mediumModel,
        medium_key: keys[mediumProvider] || 'local',
        medium_base_url: keys[`${mediumProvider}_url`] || null,
        
        directive: customDirective || null
      });

      setTweets(res.data.tweets || []);
      setArticle(res.data.article || '');
      setDirective('');
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || err.message);
    } finally {
      clearInterval(stageInterval);
      setIsProcessing(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  if (!job) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/95 backdrop-blur-2xl">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0" onClick={onClose} />
      
      <motion.div 
        initial={{ opacity: 0, scale: 0.96, y: 30 }} 
        animate={{ opacity: 1, scale: 1, y: 0 }} 
        exit={{ opacity: 0, scale: 0.96, y: 30 }} 
        className="relative z-10 w-full max-w-5xl bg-[#0e0e10] border border-white/10 rounded-[48px] shadow-[0_50px_100px_rgba(0,0,0,0.85)] overflow-hidden flex flex-col md:flex-row h-[90vh] md:h-[80vh] max-h-[850px]"
      >
        {/* Left Side: Video Details Panel */}
        <div className="flex-1 bg-black/25 flex flex-col justify-between p-12 border-b md:border-b-0 md:border-r border-white/5 relative overflow-hidden">
          <div className="absolute w-[300px] h-[300px] rounded-full bg-primary/5 blur-[120px] -top-24 -left-24 pointer-events-none" />
          
          <div className="space-y-8 relative z-10">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-primary">
                <Globe className="w-5 h-5 text-primary" />
              </div>
              <div>
                <span className="text-[8px] font-black uppercase tracking-widest text-primary">Complete Source File</span>
                <h4 className="text-xs font-bold text-white tracking-widest uppercase">Repurposing Engine</h4>
              </div>
            </div>

            <div className="space-y-4">
              <h2 className="text-white font-black text-2xl leading-tight uppercase italic tracking-tight line-clamp-4 select-text">
                {job.video_url}
              </h2>
              <p className="text-xs text-text-dim leading-relaxed font-medium">
                The entire narrative structure of the long-form widescreen video is parsed in its entirety, extracting timestamps, logical core arguments, and technical highlights.
              </p>
            </div>
            
            <div className="space-y-4">
              <div className="p-5.5 rounded-3xl bg-white/5 border border-white/5 space-y-3">
                <p className="text-[9px] font-black text-white uppercase tracking-widest">Selected AI Scribes</p>
                <div className="space-y-2">
                  <div className="flex justify-between items-center text-[9px] font-bold">
                    <span className="text-text-dim">TWITTER:</span>
                    <span className="text-primary uppercase">{twitterProvider} ({twitterModel})</span>
                  </div>
                  <div className="flex justify-between items-center text-[9px] font-bold">
                    <span className="text-text-dim">MEDIUM:</span>
                    <span className="text-primary uppercase">{mediumProvider} ({mediumModel})</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="pt-6 relative z-10">
            <button 
              onClick={onClose} 
              className="w-full bg-white/5 border border-white/10 text-white/50 py-4.5 rounded-[22px] text-[10px] font-black uppercase tracking-[0.2em] hover:bg-white/10 hover:text-white transition-all active:scale-95 cursor-pointer flex items-center justify-center gap-2"
            >
              Back to Dashboard
            </button>
          </div>
        </div>

        {/* Right Side: Tabbed Repurposing Outputs */}
        <div className="w-full md:w-[480px] p-12 flex flex-col justify-between overflow-y-auto bg-[#121214] z-10">
          {isLoading ? (
            <div className="flex-1 flex flex-col items-center justify-center text-center">
              <RefreshCw className="w-8 h-8 text-primary animate-spin mb-4" />
              <p className="text-[10px] text-text-dim font-black uppercase tracking-widest animate-pulse">Syncing repurposing cache...</p>
            </div>
          ) : isProcessing ? (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-6 space-y-6">
              <div className="w-16 h-16 rounded-[24px] bg-primary/10 border border-primary/20 flex items-center justify-center relative">
                <motion.div 
                  animate={{ rotate: 360 }}
                  transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
                  className="absolute inset-2 border-2 border-transparent border-t-primary rounded-full"
                />
                <Cpu className="text-primary w-6 h-6 animate-pulse" />
              </div>
              <div className="space-y-2">
                <p className="text-[9px] font-black uppercase tracking-[0.3em] text-primary">Content AI Processing</p>
                <p className="text-[10px] text-white/60 font-medium leading-relaxed max-w-[280px] transition-all">{processingMsg}</p>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col justify-between h-full space-y-6">
              {error && (
                <div className="p-4.5 rounded-2xl bg-red-500/10 border border-red-500/20 text-red-400 text-[9px] font-black uppercase tracking-wide leading-relaxed">
                  {error}
                </div>
              )}

              {tweets.length === 0 && !article ? (
                /* Welcome / Ingest State */
                <div className="flex-1 flex flex-col items-center justify-center text-center p-4 space-y-6">
                  <div className="w-20 h-20 rounded-[32px] bg-white/5 border border-white/10 flex items-center justify-center text-white/20 shadow-2xl relative">
                    <motion.div animate={{ scale: [1, 1.15, 1] }} transition={{ repeat: Infinity, duration: 4 }} className="absolute inset-0 bg-primary/5 blur-xl rounded-full" />
                    <Sparkles className="w-8 h-8 text-primary/30 animate-pulse" />
                  </div>
                  <div className="space-y-2">
                    <h3 className="text-xl font-bold text-white uppercase italic tracking-wider">Unprocessed Source</h3>
                    <p className="text-xs text-text-dim leading-relaxed max-w-[280px] font-medium">No repurposed content has been created for this complete video yet. Ingest subtitles and run the dual-model generator floor.</p>
                  </div>
                  <button 
                    onClick={() => handleRepurpose()}
                    className="w-full bg-primary text-black py-4.5 rounded-[22px] text-[10px] font-black uppercase tracking-[0.2em] hover:scale-[1.02] shadow-[0_10px_30px_rgba(255,255,0,0.1)] active:scale-95 transition-all flex items-center justify-center gap-2 cursor-pointer font-bold mt-4"
                  >
                    <Sparkles className="w-4 h-4 fill-current animate-pulse" /> Ingest & Repurpose Video
                  </button>
                </div>
              ) : (
                /* Main Content Tabs */
                <div className="flex-1 flex flex-col justify-between h-full space-y-8">
                  <div className="space-y-6 flex-1 flex flex-col min-h-0">
                    {/* Tab Selector */}
                    <div className="flex bg-black/45 p-1 rounded-2xl border border-white/5">
                      <button 
                        onClick={() => setTab('tweets')} 
                        className={`flex-1 py-3 px-4 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${tab === 'tweets' ? 'bg-white/5 text-primary shadow-lg border border-white/5' : 'text-text-dim hover:text-white'}`}
                      >
                        Twitter Thread 🐦
                      </button>
                      <button 
                        onClick={() => setTab('medium')} 
                        className={`flex-1 py-3 px-4 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${tab === 'medium' ? 'bg-white/5 text-primary shadow-lg border border-white/5' : 'text-text-dim hover:text-white'}`}
                      >
                        Medium Article 📝
                      </button>
                    </div>

                    {/* Tab Content Panels */}
                    <div className="flex-1 overflow-y-auto max-h-[44vh] scrollbar-thin pr-1 min-h-0">

                  {tab === 'tweets' ? (
                    /* Twitter Timeline mockup with fypd's glassmorphic neon aesthetic */
                    <div className="space-y-4">
                      {tweets.map((tweet, idx) => (
                        <div key={idx} className="flex gap-4 items-start relative group">
                          {/* Vertical reply connector line with a neon blue/purple gradient glow */}
                          {idx < tweets.length - 1 && (
                            <div className="absolute left-[17px] top-[40px] bottom-[-24px] w-[2px] bg-gradient-to-b from-[#00ffff] to-[#bd00ff] opacity-40 shadow-[0_0_8px_rgba(0,255,255,0.3)]" />
                          )}

                          {/* Profile Avatar Grid */}
                          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#00ffff] to-[#bd00ff] flex items-center justify-center text-xs font-black text-black flex-shrink-0 shadow-[0_0_15px_rgba(0,255,255,0.15)] select-none">
                            AI
                          </div>

                          {/* Tweet body */}
                          <div className="flex-1 bg-white/[0.02] border border-white/5 rounded-2xl p-5.5 space-y-2.5 transition-all group-hover:border-white/10 relative overflow-hidden group-hover:bg-white/[0.04] shadow-lg">
                            <div className="flex justify-between items-center">
                              <div className="flex items-center gap-1.5">
                                <span className="text-[10px] font-black text-white">fypd scribe</span>
                                <span className="text-[8.5px] font-medium text-text-dim">@fypd_scribe</span>
                              </div>
                              <span className="text-[8px] text-white/20 font-bold uppercase">Tweet {idx + 1}</span>
                            </div>
                            <p className="text-[11.5px] text-white/80 leading-relaxed font-medium whitespace-pre-wrap select-text">{tweet}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    /* Medium Article Panel */
                    <div className="bg-white/[0.02] border border-white/5 rounded-[32px] p-8 space-y-6 select-text shadow-lg">
                      <div className="prose prose-invert prose-xs text-[#d1d1d6] leading-relaxed max-w-none font-sans font-medium">
                        <div className="whitespace-pre-wrap text-[12px] font-sans">
                          {article}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Refinement Inputs & Actions */}
              <div className="space-y-4 pt-6 border-t border-white/5">
                <div className="flex gap-2">
                  <button 
                    onClick={() => {
                      if (tab === 'tweets') {
                        copyToClipboard(tweets.join("\n\n---\n\n"));
                      } else {
                        copyToClipboard(article);
                      }
                    }} 
                    className="flex-1 bg-white/5 border border-white/10 hover:bg-white/10 text-white/80 py-4 rounded-[18px] text-[9px] font-black uppercase tracking-[0.2em] transition-all flex items-center justify-center gap-2 cursor-pointer"
                  >
                    {isCopied ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-green-400" />
                        <span className="text-green-400">Copied Scribe!</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5 text-primary" />
                        <span>Copy {tab === 'tweets' ? 'Thread' : 'Article'}</span>
                      </>
                    )}
                  </button>
                </div>

                <div className="relative">
                  <input 
                    type="text" 
                    value={directive} 
                    onChange={(e) => setDirective(e.target.value)} 
                    placeholder={`Refine ${tab === 'tweets' ? 'thread' : 'article'}... (e.g. "make it controversial")`} 
                    className="w-full bg-black/45 border border-white/10 rounded-[22px] pl-6 pr-24 py-4.5 text-xs focus:outline-none focus:border-primary/50 text-white placeholder:text-white/20 transition-colors"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && directive.trim()) {
                        handleRepurpose(directive.trim());
                      }
                    }}
                  />
                  <button 
                    onClick={() => handleRepurpose(directive.trim())}
                    disabled={!directive.trim()}
                    className="absolute right-2 top-2 bottom-2 bg-primary text-black px-5 rounded-[16px] text-[8.5px] font-black uppercase tracking-wider hover:scale-[1.02] active:scale-95 transition-all cursor-pointer disabled:opacity-30 disabled:scale-100 disabled:pointer-events-none"
                  >
                    Regen
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
      </motion.div>
    </div>
  );
};

interface CinemaPlayerModalProps {
  video: {
    videoUrl: string;
    title: string;
    caption: string;
    style: string;
    start: string;
    end: string;
    bgmMood?: string;
  } | null;
  onClose: () => void;
}

const CinemaPlayerModal: React.FC<CinemaPlayerModalProps> = ({ video, onClose }) => {
  const [isPlaying, setIsPlaying] = useState(true);
  const [isCopied, setIsCopied] = useState(false);
  const videoRef = React.useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (video) {
      setIsPlaying(true);
      setIsCopied(false);
    }
  }, [video]);

  if (!video) return null;

  const handlePlayPause = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
      } else {
        videoRef.current.play();
      }
      setIsPlaying(!isPlaying);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(video.caption);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  let glowColor = "rgba(255, 255, 255, 0.12)";
  let activeTheme = "Minimalist Theme";
  let badgeColor = "border-white/20 bg-white/5 text-white";

  if (video.style === 'hormozi') {
    glowColor = "rgba(255, 255, 0, 0.15)";
    activeTheme = "Hormozi Kinetic";
    badgeColor = "border-primary/20 bg-primary/5 text-primary";
  } else if (video.style === 'neon') {
    glowColor = "rgba(0, 255, 255, 0.2)";
    activeTheme = "Neon Glow Style";
    badgeColor = "border-[#00ffff]/20 bg-[#00ffff]/5 text-[#00ffff]";
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/95 backdrop-blur-2xl">
      <motion.div 
        initial={{ opacity: 0 }} 
        animate={{ opacity: 1 }} 
        exit={{ opacity: 0 }} 
        className="absolute inset-0" 
        onClick={onClose} 
      />
      
      <motion.div 
        initial={{ opacity: 0, scale: 0.96, y: 30 }} 
        animate={{ opacity: 1, scale: 1, y: 0 }} 
        exit={{ opacity: 0, scale: 0.96, y: 30 }} 
        className="relative z-10 w-full max-w-5xl bg-[#0e0e10] border border-white/10 rounded-[48px] shadow-[0_50px_100px_rgba(0,0,0,0.85)] overflow-hidden flex flex-col md:flex-row h-[90vh] md:h-[80vh] max-h-[850px]"
      >
        <div className="flex-1 bg-black flex items-center justify-center relative p-8 border-b md:border-b-0 md:border-r border-white/5 overflow-hidden">
          <div 
            className="absolute w-[300px] h-[300px] rounded-full blur-[100px] pointer-events-none transition-all duration-700 animate-pulse" 
            style={{ backgroundColor: glowColor, transform: "scale(1.2)" }} 
          />

          <div className="relative aspect-[9/16] h-full max-h-[70vh] rounded-[32px] overflow-hidden border border-white/10 shadow-2xl z-10 bg-[#060608]">
            <video 
              ref={videoRef}
              src={video.videoUrl} 
              autoPlay
              controls
              playsInline
              onPlay={() => setIsPlaying(true)}
              onPause={() => setIsPlaying(false)}
              className="w-full h-full object-cover cursor-pointer"
              onClick={handlePlayPause}
            />
          </div>
        </div>

        <div className="w-full md:w-[420px] p-12 flex flex-col justify-between overflow-y-auto bg-[#121214] z-10">
          <div className="space-y-8">
            <div className="flex justify-between items-center">
              <span className={`px-3 py-1.5 rounded-xl border text-[8px] font-black uppercase tracking-[0.25em] ${badgeColor}`}>
                {activeTheme}
              </span>
              <button 
                onClick={onClose} 
                className="w-10 h-10 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-white/50 hover:text-white hover:bg-white/10 transition-all active:scale-95 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4">
              <h2 className="text-white font-black text-3xl leading-tight uppercase italic tracking-tight">
                {video.title}
              </h2>
              
              <div className="flex flex-wrap items-center gap-2.5 text-text-dim text-[8px] font-black uppercase tracking-widest">
                <span className="flex items-center gap-1.5 bg-white/5 px-2.5 py-1.5 rounded-lg border border-white/5">
                  <Clock className="w-3 h-3 text-primary" /> {video.start}
                </span>
                <span className="opacity-20">—</span>
                <span className="flex items-center gap-1.5 bg-white/5 px-2.5 py-1.5 rounded-lg border border-white/5">
                  {video.end}
                </span>
                {video.bgmMood && (
                  <>
                    <span className="opacity-20">—</span>
                    <span className="flex items-center gap-1.5 bg-white/5 px-2.5 py-1.5 rounded-lg border border-white/5">
                      BGM: {video.bgmMood}
                    </span>
                  </>
                )}
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <label className="text-[9px] font-black text-text-dim uppercase tracking-[0.2em] flex items-center gap-1.5">
                  <Sparkles className="w-3 h-3 text-primary animate-pulse" /> Caption Transcript
                </label>
                <span className="text-[8px] text-white/20 font-bold uppercase tracking-widest">Auto-Aligned</span>
              </div>
              <div className="bg-black/45 p-6 rounded-[28px] border border-white/5 relative overflow-hidden max-h-[180px] overflow-y-auto scrollbar-thin">
                <div className="absolute top-0 left-0 w-1 h-full bg-primary/20" />
                <p className="text-[11.5px] text-white/70 leading-relaxed font-medium">
                  {video.caption || "Awaiting transcription metadata..."}
                </p>
              </div>
            </div>

            {isPlaying && (
              <div className="pt-4 flex items-center justify-between border-t border-white/5">
                <span className="text-[8px] font-black uppercase tracking-[0.2em] text-white/30 flex items-center gap-1.5">
                  <Volume2 className="w-3 h-3 text-primary animate-pulse" /> Spliced Audio Active
                </span>
                <div className="flex gap-0.5 items-end h-3 pr-1">
                  {[...Array(6)].map((_, i) => (
                    <motion.div 
                      key={i}
                      animate={{ 
                        height: [3, 12, 3],
                      }}
                      transition={{ 
                        repeat: Infinity, 
                        duration: 0.5 + i * 0.12,
                        ease: "easeInOut"
                      }}
                      className="w-[2px] bg-primary rounded-full" 
                    />
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="mt-8 space-y-3">
            <button 
              onClick={handleCopy} 
              className="w-full bg-white/5 border border-white/10 hover:bg-white/10 text-white/80 py-4.5 rounded-[22px] text-[10px] font-black uppercase tracking-[0.2em] transition-all flex items-center justify-center gap-2.5 cursor-pointer"
            >
              {isCopied ? (
                <>
                  <Check className="w-4 h-4 text-green-400" />
                  <span className="text-green-400">Copied to Clipboard</span>
                </>
              ) : (
                <>
                  <Copy className="w-4 h-4 text-primary" />
                  <span>Copy Caption Metadata</span>
                </>
              )}
            </button>
            <a 
              href={video.videoUrl} 
              download={`fypd_${video.title.replace(/\s+/g, '_')}.mp4`}
              className="w-full bg-primary text-black py-4.5 rounded-[22px] text-[10px] font-black uppercase tracking-[0.2em] hover:scale-[1.02] active:scale-[0.98] transition-all shadow-[0_10px_30px_rgba(255,255,0,0.1)] flex items-center justify-center gap-2.5 cursor-pointer text-center font-bold"
            >
              <Download className="w-4 h-4" />
              <span>Download Raw Short</span>
            </a>
          </div>
        </div>
      </motion.div>
    </div>
  );
};

const JobCard: React.FC<{ 
  job: Job, 
  clip: Clip, 
  onOpenCinema: (url: string, title: string, caption: string, style: string, start: string, end: string, bgmMood?: string) => void 
}> = ({ job, clip, onOpenCinema }) => {
  const videoUrl = `${API_BASE}/videos/SmartShort_${clip.id}_${clip.title}.mp4`;
  const [elapsed, setElapsed] = useState(0);
  const status = clip.status || job.status;

  useEffect(() => {
    let interval: any;
    if (status === 'processing' || (job.status === 'processing' && !clip.status)) {
      interval = setInterval(() => {
        setElapsed(prev => prev + 1);
      }, 1000);
    } else {
      setElapsed(0);
    }
    return () => clearInterval(interval);
  }, [status, job.status]);

  return (
    <motion.div layout initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.9 }} className="group">
      <div className="bg-[#121214] rounded-[40px] overflow-hidden border border-white/5 transition-all group-hover:border-white/20 shadow-2xl group-hover:shadow-primary/5">
        
        <div className="aspect-[4/5] bg-black relative overflow-hidden border-b border-white/5">
          {status === 'completed' ? (
            <div 
              onClick={() => onOpenCinema(videoUrl, clip.title, clip.caption || '', clip.style || 'hormozi', clip.start_time, clip.end_time, clip.bgm_mood)}
              className="relative w-full h-full cursor-pointer group/vid overflow-hidden"
            >
              <video 
                src={videoUrl} 
                muted 
                playsInline 
                loop
                onMouseEnter={(e) => e.currentTarget.play().catch(() => {})}
                onMouseLeave={(e) => {
                  e.currentTarget.pause();
                  e.currentTarget.currentTime = 0;
                }}
                className="w-full h-full object-cover transition-transform duration-700 group-hover/vid:scale-105" 
              />
              <div className="absolute inset-0 bg-black/40 opacity-0 group-hover/vid:opacity-100 transition-opacity duration-300 flex items-center justify-center">
                <div className="w-16 h-16 rounded-full bg-primary/20 backdrop-blur-md border border-primary/50 flex items-center justify-center shadow-[0_0_20px_rgba(255,255,0,0.3)] transition-transform duration-300 group-hover/vid:scale-110">
                  <Play className="w-5 h-5 text-primary fill-current ml-1 animate-pulse" />
                </div>
              </div>
              <div className="absolute bottom-4 right-4 bg-black/70 backdrop-blur-md border border-white/10 px-2.5 py-1 rounded-md text-[8px] font-black uppercase tracking-wider text-white flex items-center gap-1">
                Hover to Preview
              </div>
            </div>
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center p-8 text-center bg-[#0d0d0f]">
              <div className="relative mb-6">
                <motion.div animate={{ scale: [1, 1.3, 1], opacity: [0.1, 0.3, 0.1] }} transition={{ repeat: Infinity, duration: 3 }} className="absolute inset-0 bg-primary/20 blur-2xl rounded-full" />
                <div className="w-16 h-16 rounded-[24px] bg-white/5 border border-white/10 flex items-center justify-center relative z-10">
                   <Cpu className={`w-6 h-6 ${status === 'failed' ? 'text-red-500' : 'text-primary'}`} />
                </div>
              </div>
              <p className="text-[9px] font-black uppercase tracking-[0.4em] text-white/40 mb-3">{status === 'failed' ? 'Engine Fault' : status}</p>
              
              {status === 'processing' || (job.status === 'processing' && !clip.status) ? (
                <ProcessingPhaseTracker elapsedSeconds={elapsed} progress={clip.progress} />
              ) : status === 'failed' ? (
                <div className="text-[8.5px] text-red-400 bg-red-500/10 border border-red-500/25 px-4.5 py-3 rounded-2xl font-bold leading-relaxed max-w-[220px] break-words">
                  {job.error || "An unknown system pipeline exception occurred."}
                </div>
              ) : (
                <p className="text-[8px] text-text-dim uppercase tracking-widest font-black animate-pulse">Waiting in execution queue...</p>
              )}
            </div>
          )}
          <div className="absolute top-6 left-6 z-20">
            <div className={`px-3 py-1.5 rounded-xl text-[8px] font-black uppercase tracking-[0.2em] backdrop-blur-md border ${status === 'completed' ? 'bg-green-500/10 border-green-500/30 text-green-400' : status === 'failed' ? 'bg-red-500/10 border-red-500/30 text-red-400' : 'bg-primary/10 border-primary/30 text-primary animate-pulse'}`}>
              {status}
            </div>
          </div>
        </div>

        <div className="p-8 space-y-6 bg-[#121214]">
          <div className="space-y-2">
            <div className="flex justify-between items-start gap-4">
               <h3 className="text-white font-black text-lg leading-tight group-hover:text-primary transition-colors line-clamp-2 uppercase italic tracking-tight">{clip.title}</h3>
               {status === 'completed' && (
                 <ExternalLink className="w-4 h-4 text-white/20 hover:text-primary cursor-pointer flex-shrink-0 transition-colors" onClick={() => window.open(videoUrl)} />
               )}
            </div>
            <div className="flex items-center gap-3 text-text-dim text-[8px] font-black uppercase tracking-widest">
               <span className="flex items-center gap-1.5 bg-white/5 px-2.5 py-1.5 rounded-lg border border-white/5"><Clock className="w-3 h-3 text-primary" /> {clip.start_time}</span>
               <span className="opacity-20">—</span>
               <span className="flex items-center gap-1.5 bg-white/5 px-2.5 py-1.5 rounded-lg border border-white/5">{clip.end_time}</span>
            </div>
          </div>
          <div className="bg-black/30 p-5 rounded-[20px] border border-white/5 relative overflow-hidden">
            <div className="absolute top-0 left-0 w-1 h-full bg-primary/20 group-hover:bg-primary/50 transition-colors" />
            <p className="text-[10px] text-white/45 leading-relaxed font-medium line-clamp-3">
              {clip.caption || "Awaiting transcription metadata..."}
            </p>
          </div>
          <div className="pt-1">
            <button 
              disabled={job.status !== 'completed'} 
              onClick={() => {
                navigator.clipboard.writeText(clip.caption || '');
                alert("Caption metadata copied to clipboard.");
              }} 
              className="w-full bg-white/5 border border-white/10 text-white/40 py-3.5 rounded-[18px] text-[8.5px] font-black uppercase tracking-[0.2em] hover:bg-white/10 hover:text-white transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-30 disabled:pointer-events-none"
            >
              <Copy className="w-3.5 h-3.5 text-primary" /> Copy Caption
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

export default App;
