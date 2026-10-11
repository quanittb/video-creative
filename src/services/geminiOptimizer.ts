import { AdCopyBrief, AD_COPY_STYLES, VOICE_EXPRESSIONS } from "../data/adCopyOptions";
import { TtsVoice, getVoiceLanguage } from "../data/ttsVoices";

export interface OptimizationResult {
  originalScript: string;
  optimizedScript: string;
  /** Kept as stable result properties; these now identify the ad-copy style, not the visual scene preset. */
  styleId: string;
  styleName: string;
  source: "gemini_api" | "offline_template";
  tokensUsed?: number;
  wordCountOriginal: number;
  wordCountOptimized: number;
  estimatedSecOriginal: number;
  estimatedSecOptimized: number;
  targetLanguage: string;
  targetLanguageName: string;
  voiceName: string;
  modelUsed?: string;
  recommendedExpressionId: string;
  recommendedExpressionName: string;
  recommendationRationale: string;
  fallbackReason?: string;
}

const STORAGE_KEY = "VCS_GEMINI_API_KEY";
const STORAGE_MODEL_KEY = "VCS_GEMINI_MODEL";

export function getStoredGeminiKey(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

export function setStoredGeminiKey(key: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, key.trim());
  } catch {
    // ignore
  }
}

export function getStoredGeminiModel(): string {
  try {
    return localStorage.getItem(STORAGE_MODEL_KEY) || "gemini-2.5-flash";
  } catch {
    return "gemini-2.5-flash";
  }
}

export function setStoredGeminiModel(model: string): void {
  try {
    localStorage.setItem(STORAGE_MODEL_KEY, model.trim());
  } catch {
    // ignore
  }
}

export async function fetchAvailableGeminiModels(apiKey: string): Promise<string[]> {
  try {
    const resp = await fetch(`https://generativelanguage.googleapis.com/v1beta/models?key=${apiKey}`);
    if (!resp.ok) return [];
    const data = await resp.json();
    const models: Array<{ name: string; supportedGenerationMethods?: string[] }> = data.models || [];
    return models
      .filter((model) => model.supportedGenerationMethods?.includes("generateContent"))
      .map((model) => model.name.replace(/^models\//, ""));
  } catch (err) {
    console.warn("Lỗi lấy danh sách models Gemini:", err);
    return [];
  }
}

export async function getBestAvailableGeminiModel(apiKey: string): Promise<string> {
  const models = await fetchAvailableGeminiModels(apiKey);
  if (models.length === 0) return getStoredGeminiModel() || "gemini-2.5-flash";
  const flashModels = models.filter((model) => model.toLowerCase().includes("flash"));
  if (flashModels.length > 0) {
    flashModels.sort((a, b) => b.localeCompare(a));
    return flashModels[0];
  }
  return models[0];
}

const OBJECTIVE_LABELS: Record<string, string> = {
  awareness: "brand awareness",
  consideration: "product consideration",
  conversion: "purchase/conversion",
  lead: "lead generation",
  app_install: "app installation",
};

function getDefaultBrief(): AdCopyBrief {
  return {
    styleId: "ugc_creator",
    marketId: "VN",
    marketName: "Việt Nam",
    audience: "",
    objective: "awareness",
    durationSeconds: 30,
    productFacts: "",
    callToAction: "",
  };
}

function normalizeBrief(brief?: Partial<AdCopyBrief>): AdCopyBrief {
  const fallback = getDefaultBrief();
  return { ...fallback, ...brief };
}

function guessExpression(voice: TtsVoice | null | undefined, adStyleId: string, objective: string): string {
  const voiceProfile = `${voice?.description || ""} ${(voice?.tags || []).join(" ")} ${voice?.category || ""}`.toLowerCase();
  if (/(calm|meditation|thiền|tĩnh tâm|trầm|reassur)/.test(voiceProfile)) return "calm_reassuring";
  if (/(hài|vui nhộn|playful|tốp tốp|tiktok)/.test(voiceProfile) || adStyleId === "ugc_creator") return "energetic_upbeat";
  if (/(news|tin tức|phát thanh|professional|business|chuyên nghiệp)/.test(voiceProfile)) return "confident_trustworthy";
  if (objective === "conversion" || objective === "lead") return "confident_trustworthy";
  return "warm_friendly";
}

/** Build the ad-specific constraints separately from the selected visual studio scene. */
export function buildAdCopySystemInstruction(
  targetVoice: TtsVoice | null | undefined,
  briefInput?: Partial<AdCopyBrief>,
  selectedExpressionId = "natural_clear",
): string {
  const brief = normalizeBrief(briefInput);
  const style = AD_COPY_STYLES.find((item) => item.id === brief.styleId) || AD_COPY_STYLES[0];
  const expression = VOICE_EXPRESSIONS.find((item) => item.id === selectedExpressionId) || VOICE_EXPRESSIONS[0];
  const langInfo = getVoiceLanguage(targetVoice);
  const market = brief.marketId === "other"
    ? (brief.customMarket?.trim() || "the market specified by the user")
    : brief.marketName;
  const voiceProfile = targetVoice
    ? `${targetVoice.name} (${targetVoice.gender}, ${targetVoice.description}; locale ${targetVoice.lang || langInfo.locale})`
    : `unspecified voice (${langInfo.name})`;

  return `[ROLE]\nYou are an experienced short-form video ad copywriter and localization editor.\n\n` +
    `[AD BRIEF]\n` +
    `- Creative format: ${style.label}. ${style.guidance}\n` +
    `- Target market: ${market}${brief.marketId !== "other" ? ` (${brief.marketId})` : ""}. Adapt idioms, formality, humor and cultural references cautiously to this market; do not stereotype or assume every audience shares one norm.\n` +
    `- Target audience: ${brief.audience.trim() || "not specified"}\n` +
    `- Campaign objective: ${OBJECTIVE_LABELS[brief.objective] || brief.objective}\n` +
    `- Target duration: about ${brief.durationSeconds} seconds of spoken copy. Use a natural pace for the chosen language; this is an estimate, not a hard timing guarantee.\n` +
    `- Product / service facts supplied by the user: ${brief.productFacts.trim() || "none supplied separately; use only facts present in the source script"}\n` +
    `- Requested CTA: ${brief.callToAction.trim() || "none specified; use a simple, non-pressuring invitation only if appropriate"}\n` +
    `- Selected voice: ${voiceProfile}\n` +
    `- Desired delivery direction: ${expression.label}. ${expression.guidance}\n\n` +
    `[REQUIRED RULES]\n` +
    `1. Write the spoken ad in ${langInfo.name}, matching the selected voice language. Localize wording for the target market without changing facts.\n` +
    `2. Treat the source script and supplied product facts as the complete evidence. Preserve names, prices, quantities, qualifiers and conditions exactly. Do not invent product features, outcomes, statistics, medical/financial claims, guarantees, testimonials, certifications, scarcity, discounts or legal claims.\n` +
    `3. If evidence is missing, omit the claim rather than filling the gap. Never present invented first-person customer experience as real UGC. Do not create false urgency.\n` +
    `4. Use the selected creative format, audience, objective, duration and requested CTA to shape the hook, structure, sentence length and pacing. Keep the delivery direction consistent with the selected voice profile.\n` +
    `5. Return valid JSON only, with keys: "optimizedScript" (spoken copy only, no stage directions or explanations), "recommendedExpressionId" (one of ${VOICE_EXPRESSIONS.map((item) => item.id).join(", ")}), and "recommendationRationale" (one concise sentence in Vietnamese explaining why the direction suits this voice and ad).`;
}

function parseModelOutput(text: string): { script: string; expressionId?: string; rationale?: string } {
  const unfenced = text.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  try {
    const parsed = JSON.parse(unfenced);
    const script = typeof parsed?.optimizedScript === "string" ? parsed.optimizedScript.trim() : "";
    const expressionId = VOICE_EXPRESSIONS.some((item) => item.id === parsed?.recommendedExpressionId)
      ? parsed.recommendedExpressionId as string
      : undefined;
    const rationale = typeof parsed?.recommendationRationale === "string" ? parsed.recommendationRationale.trim() : undefined;
    if (script) return { script, expressionId, rationale };
  } catch {
    // Keep compatibility with model responses that ignore the JSON instruction.
  }
  if (unfenced.startsWith("{")) throw new Error("Gemini trả về JSON không hợp lệ.");
  return { script: unfenced };
}

export async function optimizeScriptWithGemini(
  script: string,
  adStyleId: string,
  targetVoice?: TtsVoice | null,
  customApiKey?: string,
  adBrief?: Partial<AdCopyBrief>,
  selectedExpressionId = "natural_clear",
): Promise<OptimizationResult> {
  const trimmed = script.trim();
  if (!trimmed) throw new Error("Kịch bản đang trống. Vui lòng nhập nội dung kịch bản trước khi tối ưu.");

  const brief = normalizeBrief({ ...adBrief, styleId: adStyleId });
  const adStyle = AD_COPY_STYLES.find((item) => item.id === brief.styleId) || AD_COPY_STYLES[0];
  const apiKey = (customApiKey || getStoredGeminiKey()).trim();
  const langInfo = getVoiceLanguage(targetVoice);
  const voiceName = targetVoice?.name || "Giọng mặc định";
  const systemPrompt = buildAdCopySystemInstruction(targetVoice, brief, selectedExpressionId);
  const wordsOriginal = trimmed.split(/\s+/).length;
  const secOriginal = Math.round((wordsOriginal / 140) * 60);
  let fallbackReason: string | undefined;

  if (apiKey) {
    try {
    let activeModel = getStoredGeminiModel() || "gemini-2.5-flash";
    const payload = {
      contents: [{
        role: "user",
        parts: [{ text: `Tối ưu phần lời thoại quảng cáo dựa trên brief ở system instruction.\n\nNguồn nội dung của người dùng:\n"""\n${trimmed}\n"""\n\nKhông được bổ sung dữ kiện ngoài nội dung này và phần thông tin sản phẩm đã cung cấp.` }],
      }],
      systemInstruction: { parts: [{ text: systemPrompt }] },
      generationConfig: { temperature: 0.45, topP: 0.9, maxOutputTokens: 2048, responseMimeType: "application/json" },
    };
    const sendRequest = (model: string) => fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
    );

    let response = await sendRequest(activeModel);
    if (!response.ok) {
      const errorJson = await response.clone().json().catch(() => null);
      const message = errorJson?.error?.message || "";
      if (response.status === 404 || /not found|not supported|ListModels/i.test(message)) {
        const bestModel = await getBestAvailableGeminiModel(apiKey);
        if (bestModel && bestModel !== activeModel) {
          activeModel = bestModel;
          setStoredGeminiModel(bestModel);
          response = await sendRequest(bestModel);
        }
      }
    }
    if (!response.ok) {
      const errorJson = await response.json().catch(() => null);
      throw new Error(`Google Gemini API báo lỗi: ${errorJson?.error?.message || `HTTP ${response.status}`}`);
    }
    const data = await response.json();
    const candidateText = data?.candidates?.[0]?.content?.parts?.[0]?.text?.trim() || "";
    if (!candidateText) throw new Error("Gemini không trả về nội dung kịch bản.");
    const result = parseModelOutput(candidateText);
    if (!result.script) throw new Error("Không đọc được lời thoại từ kết quả Gemini.");
    const recommendedExpressionId = result.expressionId || guessExpression(targetVoice, brief.styleId, brief.objective);
    const recommendation = VOICE_EXPRESSIONS.find((item) => item.id === recommendedExpressionId) || VOICE_EXPRESSIONS[0];
    const wordCountOptimized = result.script.split(/\s+/).length;
    return {
      originalScript: trimmed,
      optimizedScript: result.script,
      styleId: brief.styleId,
      styleName: adStyle.label,
      source: "gemini_api",
      tokensUsed: data?.usageMetadata?.totalTokenCount,
      wordCountOriginal: wordsOriginal,
      wordCountOptimized,
      estimatedSecOriginal: secOriginal,
      estimatedSecOptimized: Math.round((wordCountOptimized / 140) * 60),
      targetLanguage: langInfo.code,
      targetLanguageName: langInfo.name,
      voiceName,
      modelUsed: activeModel,
      recommendedExpressionId,
      recommendedExpressionName: recommendation.label,
      recommendationRationale: result.rationale || recommendation.fit,
    };
    } catch (error) {
      console.warn("Gemini API không khả dụng, dùng fallback không AI:", error);
      fallbackReason = error instanceof Error ? error.message : "Gemini API hiện không khả dụng.";
    }
  }

  // A deterministic offline fallback must never fabricate ad claims or pretend to localize.
  const offlineOptimized = trimmed.replace(/\s+/g, " ");
  const recommendedExpressionId = guessExpression(targetVoice, brief.styleId, brief.objective);
  const recommendation = VOICE_EXPRESSIONS.find((item) => item.id === recommendedExpressionId) || VOICE_EXPRESSIONS[0];
  const wordCountOptimized = offlineOptimized.split(/\s+/).length;
  return {
    originalScript: trimmed,
    optimizedScript: offlineOptimized,
    styleId: brief.styleId,
    styleName: adStyle.label,
    source: "offline_template",
    wordCountOriginal: wordsOriginal,
    wordCountOptimized,
    estimatedSecOriginal: secOriginal,
    estimatedSecOptimized: Math.round((wordCountOptimized / 140) * 60),
    targetLanguage: langInfo.code,
    targetLanguageName: langInfo.name,
    voiceName,
    recommendedExpressionId,
    recommendedExpressionName: recommendation.label,
    recommendationRationale: `${recommendation.fit} Đây là gợi ý quy tắc cục bộ, chưa được AI phân tích.`,
    fallbackReason,
  };
}
