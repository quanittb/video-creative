import React, { useState } from "react";
import { Lock, Unlock, Key, Eye, EyeOff, AlertTriangle, ShieldAlert, RefreshCw } from "lucide-react";
import { LicenseStatus } from "../../types";

interface Props {
  license: LicenseStatus | null;
  onUnlockSuccess: () => Promise<void>;
  invokeCommand: <T>(cmd: string, args?: Record<string, any>) => Promise<T>;
}

export const ActivationLockModal: React.FC<Props> = ({
  license,
  onUnlockSuccess,
  invokeCommand,
}) => {
  const [keyInput, setKeyInput] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!keyInput.trim()) {
      setErrorMessage("Vui lòng nhập mã bảo mật kích hoạt.");
      return;
    }

    setIsVerifying(true);
    setErrorMessage(null);

    try {
      await invokeCommand<LicenseStatus>("verify_license_key", { key: keyInput.trim() });
      await onUnlockSuccess();
    } catch (err: any) {
      setErrorMessage(
        typeof err === "string" ? err : err.message || "Mã kích hoạt không chính xác. Vui lòng kiểm tra lại."
      );
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex items-center justify-center p-4 select-none font-sans">
      <div className="w-full max-w-lg bg-studio-panel border-2 border-rose-600/60 rounded-2xl p-7 shadow-2xl shadow-rose-950/50 flex flex-col gap-6 text-slate-100 animate-in fade-in zoom-in-95 duration-200">
        {/* Header with warning icon */}
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-rose-950/80 border border-rose-500/50 flex items-center justify-center text-rose-400 shrink-0 shadow-lg shadow-rose-900/40">
            <ShieldAlert className="w-8 h-8" />
          </div>
          <div>
            <span className="text-[11px] font-mono font-bold uppercase tracking-widest text-rose-400 block mb-0.5">
              Khóa Bảo Mật Thiết Bị
            </span>
            <h2 className="text-lg font-bold text-slate-100">
              Thời Gian Dùng Thử 30 Ngày Đã Hết Hạn
            </h2>
          </div>
        </div>

        {/* Message */}
        <p className="text-xs text-slate-300 leading-relaxed bg-studio-card/80 p-3.5 rounded-xl border border-studio-border/70">
          Ứng dụng <strong>Video Creative Studio</strong> đã hết thời hạn dùng thử trên thiết bị này. Tất cả các tính năng kết xuất AI, tạo video và xử lý hàng loạt đã được tạm khóa.
          <br />
          <br />
          Vui lòng nhập <strong>mật khẩu bảo mật</strong> được cấp để mở khóa và kích hoạt bản quyền vĩnh viễn.
        </p>

        {/* Device ID info */}
        <div className="p-3 rounded-lg bg-studio-elevated/70 border border-studio-border/50 text-xs font-mono flex items-center justify-between">
          <span className="text-slate-400">Mã phần cứng (Device ID):</span>
          <span className="text-studio-cyan font-bold truncate max-w-[240px]" title={license?.device_id}>
            {license?.device_id || "Đang nhận diện..."}
          </span>
        </div>

        {/* Activation Form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
              <Key className="w-3.5 h-3.5 text-studio-cyan" />
              <span>Mật khẩu kích hoạt bản quyền:</span>
            </label>

            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={keyInput}
                onChange={(e) => setKeyInput(e.target.value)}
                placeholder="Nhập mã bảo mật để mở khóa..."
                autoFocus
                className="w-full bg-studio-elevated border-2 border-studio-border focus:border-studio-accent rounded-xl px-4 py-3 text-sm text-slate-100 placeholder-slate-500 outline-none pr-11 font-mono tracking-wide"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3.5 top-3.5 text-slate-400 hover:text-slate-200"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {errorMessage && (
            <div className="p-3 rounded-xl bg-rose-950/60 border border-rose-600/70 text-rose-300 text-xs flex items-center gap-2 animate-in fade-in duration-150">
              <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
              <span>{errorMessage}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={isVerifying || !keyInput.trim()}
            className="w-full py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white text-sm font-bold flex items-center justify-center gap-2 transition-all shadow-lg shadow-indigo-600/30 disabled:opacity-50"
          >
            {isVerifying ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Đang kiểm tra mã bảo mật...</span>
              </>
            ) : (
              <>
                <Unlock className="w-4 h-4" />
                <span>Mở Khóa & Kích Hoạt Vĩnh Viễn</span>
              </>
            )}
          </button>
        </form>

        <div className="text-[11px] text-slate-500 text-center font-mono">
          Bản quyền được gắn cố định với phần cứng thiết bị • Chống gian lận thời gian hệ thống
        </div>
      </div>
    </div>
  );
};
