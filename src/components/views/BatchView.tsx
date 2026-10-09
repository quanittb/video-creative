import React, { useState } from "react";
import {
  Upload,
  FileSpreadsheet,
  FileCode,
  Download,
  Plus,
  Trash2,
  Play,
  CheckCircle,
  AlertCircle,
  Clock,
  Layers,
} from "lucide-react";
import { RenderJob } from "../../types";
import { TTS_VOICES } from "../../data/ttsVoices";

interface Props {
  onBatchQueued: () => void;
  invokeCommand: <T>(cmd: string, args?: Record<string, any>) => Promise<T>;
  isTestMode: boolean;
}

interface BatchDraftItem {
  id: string;
  name: string;
  char: string;
  script: string;
  voice: string;
  multiplier: number;
  output: string;
}

export const BatchView: React.FC<Props> = ({ onBatchQueued, invokeCommand, isTestMode }) => {
  const [items, setItems] = useState<BatchDraftItem[]>([
    {
      id: "draft_1",
      name: "Tập 1 - Tin tức Trí tuệ nhân tạo",
      char: "office",
      script:
        "Xin chào quý vị, đây là bản tin tập 1 cập nhật các phát triển vượt bậc của mô hình thị giác máy tính và tổng hợp giọng nói đa vùng miền.",
      voice: "vi-VN-NamMinhNeural",
      multiplier: 0.55,
      output: "tap_1_tin_tuc_ai.mp4",
    },
    {
      id: "draft_2",
      name: "Tập 2 - Giới thiệu Mô hình 3D",
      char: "female",
      script:
        "Chào mừng các bạn đến với tập 2. Hôm nay chúng ta sẽ tìm hiểu về cách kết hợp chuyển động chân dung và đồng bộ khẩu hình trên GPU RTX 3060.",
      voice: "vi-VN-HoaiMyNeural",
      multiplier: 0.50,
      output: "tap_2_mo_hinh_3d.mp4",
    },
    {
      id: "draft_3",
      name: "Tập 3 - Đào tạo Tự động hóa",
      char: "pixar",
      script:
        "Tập 3 sẽ hướng dẫn quy trình tự động hóa hàng loạt video bài giảng chất lượng 1080p bằng manifest CSV mà không cần can thiệp thủ công.",
      voice: "vi-VN-NamMinhNeural",
      multiplier: 0.60,
      output: "tap_3_dao_tao_batch.mp4",
    },
  ]);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    new Set(["draft_1", "draft_2", "draft_3"])
  );
  const [manifestPath, setManifestPath] = useState("");
  const [isImporting, setIsImporting] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  // Toggle selection
  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === items.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(items.map((i) => i.id)));
    }
  };

  // Add blank item
  const handleAddItem = () => {
    const idx = items.length + 1;
    const newItem: BatchDraftItem = {
      id: `draft_${Date.now()}`,
      name: `Mục batch ${idx}`,
      char: "office",
      script: "Nhập nội dung kịch bản cho mục này...",
      voice: "vi-VN-NamMinhNeural",
      multiplier: 0.55,
      output: `video_batch_${idx}.mp4`,
    };
    setItems([...items, newItem]);
    setSelectedIds(new Set([...selectedIds, newItem.id]));
  };

  // Remove selected items
  const handleRemoveSelected = () => {
    const remaining = items.filter((i) => !selectedIds.has(i.id));
    setItems(remaining);
    setSelectedIds(new Set());
  };

  // Enqueue selected items
  const handleEnqueueSelected = async () => {
    const toEnqueue = items.filter((i) => selectedIds.has(i.id));
    if (toEnqueue.length === 0) {
      alert("Chưa chọn mục batch nào để thêm vào hàng đợi.");
      return;
    }

    setIsImporting(true);
    try {
      for (const item of toEnqueue) {
        const vObj = TTS_VOICES.find((v) => v.id === item.voice);
        await invokeCommand("create_job", {
          name: item.name,
          char: item.char,
          script: item.script,
          voice: item.voice,
          gender: vObj?.gender,
          voice_provider: vObj?.provider,
          multiplier: item.multiplier,
          dry_run: isTestMode,
        });
      }

      onBatchQueued();
      setBanner(`Đã thêm thành công ${toEnqueue.length} video vào Hàng đợi tuần tự!`);
      setTimeout(() => setBanner(null), 4000);
    } catch (err: any) {
      alert(`Lỗi thêm batch: ${err}`);
    } finally {
      setIsImporting(false);
    }
  };

  // Import manifest file from path
  const handleImportFile = async () => {
    if (!manifestPath.trim()) {
      alert("Vui lòng nhập đường dẫn file CSV hoặc JSON manifest.");
      return;
    }
    setIsImporting(true);
    try {
      const res = await invokeCommand<string>("import_batch_manifest", {
        file_path: manifestPath.trim(),
      });
      setBanner(res || "Đã import thành công manifest vào queue!");
      onBatchQueued();
      setTimeout(() => setBanner(null), 4000);
    } catch (err: any) {
      alert(`Lỗi import manifest: ${err}`);
    } finally {
      setIsImporting(false);
    }
  };

  // Sample CSV / JSON downloads
  const downloadSampleCsv = () => {
    const csvContent =
      "name,character,voice,multiplier,script,output_name\n" +
      '"Tin 1","office","vi-VN-NamMinhNeural",0.55,"Xin chào các bạn, đây là video batch thứ nhất.","tin_1.mp4"\n' +
      '"Tin 2","female","vi-VN-HoaiMyNeural",0.50,"Bản tin công nghệ thế giới hôm nay có nhiều điểm mới.","tin_2.mp4"\n' +
      '"Tin 3","pixar","vi-VN-NamMinhNeural",0.60,"Bài giảng 3D chuyển động tự nhiên với AI.","tin_3.mp4"\n';

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", "sample_batch_manifest.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-studio-obsidian">
      {/* Banner */}
      {banner && (
        <div className="bg-emerald-950/80 border-b border-emerald-500/30 px-6 py-2.5 flex items-center justify-between text-emerald-200 text-xs">
          <div className="flex items-center gap-2 font-medium">
            <CheckCircle className="w-4 h-4 text-emerald-400" />
            <span>{banner}</span>
          </div>
          <button onClick={() => setBanner(null)}>✕</button>
        </div>
      )}

      {/* Top Header / Importer Toolbar */}
      <div className="bg-studio-panel border-b border-studio-border p-4 flex items-center justify-between gap-4">
        {/* Manifest Path Input */}
        <div className="flex items-center gap-2 flex-1 max-w-xl">
          <div className="relative flex-1">
            <input
              type="text"
              value={manifestPath}
              onChange={(e) => setManifestPath(e.target.value)}
              placeholder="Đường dẫn file manifest (.csv hoặc .json)..."
              className="w-full bg-studio-card border border-studio-border rounded-lg pl-3 pr-8 py-1.5 text-xs text-slate-100 placeholder-slate-500 outline-none focus:border-studio-accent font-mono"
            />
          </div>
          <button
            onClick={handleImportFile}
            disabled={isImporting || !manifestPath.trim()}
            className="px-3 py-1.5 rounded-lg bg-studio-card border border-studio-border hover:border-slate-500 text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <Upload className="w-3.5 h-3.5 text-studio-cyan" />
            <span>Nạp Manifest</span>
          </button>
        </div>

        {/* Templates & Quick Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={downloadSampleCsv}
            className="px-3 py-1.5 rounded-lg bg-studio-card border border-studio-border text-slate-300 hover:text-white text-xs font-medium flex items-center gap-1.5 transition-colors"
          >
            <Download className="w-3.5 h-3.5 text-slate-400" />
            <span>Tải CSV mẫu</span>
          </button>

          <button
            onClick={handleAddItem}
            className="px-3 py-1.5 rounded-lg bg-studio-card border border-studio-border text-slate-300 hover:text-white text-xs font-medium flex items-center gap-1.5 transition-colors"
          >
            <Plus className="w-3.5 h-3.5 text-studio-cyan" />
            <span>Thêm hàng</span>
          </button>

          {selectedIds.size > 0 && (
            <button
              onClick={handleRemoveSelected}
              className="px-3 py-1.5 rounded-lg bg-studio-rose/10 border border-studio-rose/30 text-rose-300 hover:bg-studio-rose/20 text-xs font-medium flex items-center gap-1.5 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Xóa ({selectedIds.size})</span>
            </button>
          )}

          <button
            onClick={handleEnqueueSelected}
            disabled={isImporting || selectedIds.size === 0}
            className="px-4 py-1.5 rounded-lg bg-studio-accent hover:bg-studio-accentHover text-white text-xs font-semibold flex items-center gap-2 shadow-md shadow-indigo-600/20 transition-all disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>Gửi {selectedIds.size} video vào Queue</span>
          </button>
        </div>
      </div>

      {/* Main Table Area */}
      <div className="flex-1 overflow-auto p-6">
        <div className="bg-studio-card border border-studio-border rounded-xl overflow-hidden shadow-sm">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-studio-panel border-b border-studio-border text-slate-400 font-semibold uppercase tracking-wider text-[11px]">
                <th className="p-3.5 w-10 text-center">
                  <input
                    type="checkbox"
                    checked={selectedIds.size === items.length && items.length > 0}
                    onChange={toggleSelectAll}
                    className="rounded bg-studio-elevated border-studio-border text-indigo-500 focus:ring-0 cursor-pointer"
                  />
                </th>
                <th className="p-3.5 w-48">Tên video</th>
                <th className="p-3.5 w-32">Nhân vật</th>
                <th className="p-3.5 w-36">Giọng đọc</th>
                <th className="p-3.5 w-24">Biên độ</th>
                <th className="p-3.5">Kịch bản lời thoại</th>
                <th className="p-3.5 w-40">File đầu ra</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-studio-border/60">
              {items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-12 text-center text-slate-500">
                    Chưa có mục batch nào. Hãy thêm hàng mới hoặc nạp file CSV/JSON manifest.
                  </td>
                </tr>
              ) : (
                items.map((item) => {
                  const isChecked = selectedIds.has(item.id);
                  return (
                    <tr
                      key={item.id}
                      className={`hover:bg-studio-elevated/60 transition-colors ${
                        isChecked ? "bg-indigo-950/20" : ""
                      }`}
                    >
                      <td className="p-3.5 text-center">
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => toggleSelect(item.id)}
                          className="rounded bg-studio-elevated border-studio-border text-indigo-500 focus:ring-0 cursor-pointer"
                        />
                      </td>
                      <td className="p-3.5">
                        <input
                          type="text"
                          value={item.name}
                          onChange={(e) => {
                            const val = e.target.value;
                            setItems(items.map((x) => (x.id === item.id ? { ...x, name: val } : x)));
                          }}
                          className="w-full bg-transparent font-semibold text-slate-200 outline-none focus:border-b focus:border-studio-accent"
                        />
                      </td>
                      <td className="p-3.5">
                        <select
                          value={item.char}
                          onChange={(e) => {
                            const val = e.target.value;
                            setItems(items.map((x) => (x.id === item.id ? { ...x, char: val } : x)));
                          }}
                          className="w-full bg-studio-elevated border border-studio-border rounded px-2 py-1 text-slate-300 outline-none"
                        >
                          <option value="office">Asian Male (Office)</option>
                          <option value="female">Vietnamese Female</option>
                          <option value="pixar">3D Pixar Stylized</option>
                        </select>
                      </td>
                      <td className="p-3.5">
                        <select
                          value={item.voice}
                          onChange={(e) => {
                            const val = e.target.value;
                            setItems(items.map((x) => (x.id === item.id ? { ...x, voice: val } : x)));
                          }}
                          className="w-full bg-studio-elevated border border-studio-border rounded px-2 py-1 text-slate-300 outline-none"
                        >
                          <option value="vi-VN-NamMinhNeural">Nam Minh (Edge)</option>
                          <option value="vi-VN-HoaiMyNeural">Hoài My (Edge)</option>
                          <option value="en-US-GuyNeural">Guy (US)</option>
                          <option value="en-US-JennyNeural">Jenny (US)</option>
                        </select>
                      </td>
                      <td className="p-3.5 font-mono text-studio-cyan">
                        <input
                          type="number"
                          step="0.05"
                          min="0.30"
                          max="0.85"
                          value={item.multiplier}
                          onChange={(e) => {
                            const val = parseFloat(e.target.value);
                            setItems(items.map((x) => (x.id === item.id ? { ...x, multiplier: val } : x)));
                          }}
                          className="w-16 bg-studio-elevated border border-studio-border rounded px-1.5 py-1 text-slate-300 outline-none font-mono"
                        />
                      </td>
                      <td className="p-3.5">
                        <input
                          type="text"
                          value={item.script}
                          onChange={(e) => {
                            const val = e.target.value;
                            setItems(items.map((x) => (x.id === item.id ? { ...x, script: val } : x)));
                          }}
                          className="w-full bg-transparent text-slate-300 outline-none focus:border-b focus:border-studio-accent"
                        />
                      </td>
                      <td className="p-3.5 font-mono text-slate-400 text-[11px]">
                        <input
                          type="text"
                          value={item.output}
                          onChange={(e) => {
                            const val = e.target.value;
                            setItems(items.map((x) => (x.id === item.id ? { ...x, output: val } : x)));
                          }}
                          className="w-full bg-transparent text-slate-400 font-mono outline-none focus:border-b focus:border-studio-accent"
                        />
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Batch Summary Footer */}
        <div className="flex items-center justify-between mt-4 px-2 text-xs text-slate-400 font-mono">
          <div className="flex items-center gap-4">
            <span>
              Tổng số video: <strong className="text-slate-200">{items.length}</strong>
            </span>
            <span>
              Đã chọn: <strong className="text-studio-cyan">{selectedIds.size}</strong>
            </span>
          </div>
          <div className="flex items-center gap-2 text-slate-500">
            <Clock className="w-3.5 h-3.5" />
            <span>Chế độ GPU: Tuần tự 1-Job (Chống tràn 12GB VRAM)</span>
          </div>
        </div>
      </div>
    </div>
  );
};
