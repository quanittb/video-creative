import { PRESENTATION_STYLES } from "../data/presentationStyles";
import { TtsVoice, getVoiceLanguage } from "../data/ttsVoices";

export interface OptimizationResult {
  originalScript: string;
  optimizedScript: string;
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
      .filter((m) => m.supportedGenerationMethods?.includes("generateContent"))
      .map((m) => m.name.replace(/^models\//, ""));
  } catch (err) {
    console.warn("Lỗi lấy danh sách models Gemini:", err);
    return [];
  }
}

export async function getBestAvailableGeminiModel(apiKey: string): Promise<string> {
  const models = await fetchAvailableGeminiModels(apiKey);
  if (models.length === 0) {
    return getStoredGeminiModel() || "gemini-2.5-flash";
  }

  // Prioritize flash models (3.5, 3.0, 2.5, 2.0)
  const flashModels = models.filter((m) => m.toLowerCase().includes("flash"));
  if (flashModels.length > 0) {
    flashModels.sort((a, b) => b.localeCompare(a));
    return flashModels[0];
  }

  return models[0];
}

/**
 * Build style-specific directive in English for the 10 presentation styles.
 */
function getEnglishStyleDirective(styleId: string): string {
  switch (styleId) {
    case "news_anchor":
      return `You are a veteran US/UK television news anchor (like BBC or CBS News).
1. Style: Objective, authoritative, formal, high credibility.
2. Inverted Pyramid Structure: Place the single most crucial development and core takeaway in the opening two sentences, followed by key metrics, context, and a crisp conclusion.
3. Language: Crisp, active journalistic broadcast phrasing. Zero conversational filler, slang, or subjective hype.
4. Professional sign-in/out: Begin authoritatively (e.g., "Good evening. Here is today's prime briefing..."), conclude cleanly.`;

    case "educational_explainer":
      return `You are a master science and technology educator (like Veritasium, Kurzgesagt, or 3Blue1Brown).
1. Pedagogical Layout: Break the core concept into 3 digestible, progressive points (First..., Second..., and most importantly...).
2. Simplification: Use intuitive everyday metaphors and relatable analogies so complex concepts click immediately.
3. Flow & Cadence: Add smooth conversational connective phrases ("Imagine this...", "This is why...").
4. Tone: Friendly, patient, curious, and encouraging.`;

    case "cinematic_storytelling":
      return `You are an award-winning cinematic screenwriter and master voiceover narrator.
1. 3-Act Emotional Arc: Intriguing opening hook -> Rising emotional tension -> Resonant, thought-provoking conclusion.
2. Sensory Imagery: Evocative, poetic prose that paints vivid sensory pictures in the listener's mind.
3. Dramatic Breath: Insert deliberate ellipses (...) at pivotal moments where the spoken delivery should pause for dramatic weight.
4. Tone: Deep, resonant, intimate, lyrical, and deeply empathetic.`;

    case "documentary_narrator":
      return `You are a legendary documentary narrator (BBC Earth / National Geographic style).
1. Demeanor: Measured, solemn, contemplative, carrying historical gravitas and investigative authority.
2. Temporal Flow: Guide the listener across history, connecting phenomena to deeper causal truths.
3. Diction: Dignified, erudite, symbolic, and timeless. Avoid hasty buzzwords.
4. Pacing: Structured periods with deliberate, measured phrasing allowing time for reflection.`;

    case "podcast_host":
      return `You are a charismatic host of a chart-topping conversational podcast.
1. 100% Spoken Natural Cadence: Short punchy sentences, colloquial spoken phrases, friendly direct address ("you", "we").
2. Authentic Vulnerability: Include genuine spontaneous reflections ("To be completely honest...", "Have you ever wondered...?").
3. Conversational Rhythm: Open questions that make the listener feel like they are sitting across the table having coffee with a friend.
4. Avoid: Corporate jargon, robotic stiffness, or preachy lecturing.`;

    case "product_showcase":
      return `You are a high-converting Silicon Valley tech product presenter and growth marketing director.
1. High-Converting PAS/AIDA Framework:
   - Problem Hook: Target the customer's biggest frustration or wasted time directly.
   - Breakthrough Solution: Introduce the revolutionary capability.
   - 2-3 Quantifiable Benefits: Highlight concrete ROI (hours saved, 2x output, 1080p studio fidelity).
   - Irresistible Call to Action (CTA): Confident, clear closing invitation.
2. Tone: Confident, energizing, modern, value-packed, and decisive.`;

    case "motivational_speaker":
      return `You are a world-class motivational keynote speaker (Tony Robbins / Simon Sinek style).
1. Relentless Momentum: Use rhythmic repetition and parallel phrases to build escalating power ("Dare to...", "Right here, right now!", "Not tomorrow, but today!").
2. Short Declarative Power: Cut subordinate clauses; use decisive, oath-like affirmative statements.
3. Awakening Drive: Obliterate hesitation and self-doubt, ignite an urgent desire to take massive action.
4. Energy: Magnetic, resounding, electrifying conviction.`;

    case "corporate_briefing":
      return `You are a Fortune 500 Chief Strategy Officer presenting an Executive Boardroom Briefing.
1. Executive Structure:
   - Executive Summary takeaway in the first sentence.
   - Key quantitative KPIs, operational milestones, and growth metrics.
   - Actionable strategic roadmap and next steps.
2. Corporate Tone: Precise, analytical, objective, devoid of emotional fluff or speculation.
3. Credibility: Grounded in execution results and institutional rigor.`;

    case "social_creator":
      return `You are an elite viral content creator with millions of views across TikTok, Reels, and YouTube Shorts.
1. 3-Second Hook: Immediate pattern-interrupting opening that stops the scroll ("Stop scrolling right now...", "Here is what nobody tells you about...").
2. Hyper-Fast Pacing: Ultra-short sentences (< 8-10 words each), relentless snappy momentum, zero fluff.
3. Instant Value: Deliver the actionable tip or reveal within 15-30 seconds.
4. Viral Engagement CTA: Natural prompt to double-tap, bookmark, or comment.`;

    case "calm_mindful":
      return `You are a certified meditation guide and mindfulness teacher (Calm / Headspace style).
1. Gentle Cadence: Soft, soothing, grounding phrasing. Incorporate breathing cues and quiet pauses (...) for relaxation.
2. Healing Energy: Warm, accepting, non-judgmental, bringing the listener into tranquil presence.
3. Stress Dissolution: Guide the listener to gently release tension, cultivating grateful stillness.
4. Avoid: Abrupt commands, loud words, or rushing tempo.`;

    default:
      return "Optimize this script for natural, engaging, professional spoken-word voiceover delivery.";
  }
}

/**
 * Build language-specific and style-specific system instruction prompt for Gemini.
 */
function buildSystemInstruction(
  styleId: string,
  targetVoice: TtsVoice | null | undefined
): { prompt: string; targetLangCode: string; targetLangName: string; voiceName: string } {
  const style = PRESENTATION_STYLES.find((s) => s.id === styleId) || PRESENTATION_STYLES[0];
  const langInfo = getVoiceLanguage(targetVoice);
  const voiceName = targetVoice?.name || "Giọng mặc định";
  const voiceDesc = targetVoice?.description || "Giọng thuyết trình";
  const voiceGender = targetVoice?.gender === "female" ? "Nữ (Female)" : "Nam (Male)";

  let styleDirective = "";

  if (langInfo.isEnglish) {
    // English voice
    styleDirective = getEnglishStyleDirective(style.id);
  } else if (langInfo.isVietnamese) {
    // Vietnamese voice
    styleDirective = style.geminiPrompt;
  } else if (langInfo.code === "ja") {
    // Japanese voice
    styleDirective = `あなたはプロの日本語ナレーター・声優です。指定されたスタイル「${style.name}」に合わせて、自然で滑らかな日本語の話し言葉原稿に最適化・翻訳してください。
スタイル概要: ${style.scriptGuideline}
敬語・言葉遣い: スタイルに応じた適切なトーン（ニュースなら丁寧なアナウンス調、カジュアルなら親しみやすい話し言葉）を使用してください。`;
  } else if (langInfo.code === "ko") {
    // Korean voice
    styleDirective = `당신은 전문 한국어 성우이자 방송인입니다. 지정된 스타일 "${style.name}"에 맞추어 자연스럽고 생생한 한국어 음성 대본으로 최적화 및 번역해 주세요.
스타일 가이드: ${style.scriptGuideline}
어조: 스타일에 적합한 문체(뉴스/브리핑은 하십시오체, 팟캐스트/소셜은 친근한 해요체)를 일관되게 사용하세요.`;
  } else if (langInfo.code === "zh") {
    // Chinese voice
    styleDirective = `你是一名专业普通话播音员与配音演员。请将用户的口播文案优化为符合风格「${style.name}」的优质中文演讲/播报文稿。
风格准则: ${style.scriptGuideline}
语调: 吐字清晰、符合当代普通话自然口语表达节奏。`;
  } else if (langInfo.code === "es") {
    // Spanish voice
    styleDirective = `Eres un locutor profesional en idioma español. Optimiza y traduce este guion al español hablado natural y elocuente según el estilo "${style.name}".
Pautas de estilo: ${style.scriptGuideline}`;
  } else {
    styleDirective = style.geminiPrompt;
  }

  const prompt = `[ROLE & CONTEXT]
You are a world-class voiceover script director, translator, and speechwriter for an AI Video Studio.
- Target Spoken Voice: ${voiceName} (${voiceGender}, ${voiceDesc})
- Target Audio Language: ${langInfo.name} (Language Code: ${langInfo.code})
- Selected Presentation Style: #${style.number} ${style.name} (${style.vietnameseTitle})

[STYLE DIRECTIVE]
${styleDirective}

[CRITICAL INSTRUCTIONS FOR TTS SYNTHESIS]
1. OUTPUT LANGUAGE: The final optimized script MUST be written strictly in ${langInfo.name}.
   If the user's input draft is in a different language (e.g., Vietnamese draft for an English voice, or English draft for a Vietnamese voice), translate, adapt, and rewrite it idiomatically into ${langInfo.name} to sound completely native and authentic.
2. ADAPT TO VOICE PERSONA: Match the vocabulary, rhythm, and cadence to the specific voice (${voiceName}, ${voiceGender}, ${voiceDesc}).
3. SPOKEN DELIVERY ONLY: Output ONLY the spoken words ready to be read aloud by Text-To-Speech.
   - Do NOT include bracketed stage directions like [Music], [Scene 1], [Laughs], or (Pause).
   - Do NOT enclose the entire text in quotation marks or markdown code fences (\`\`\`).
   - Do NOT include polite conversational preambles like "Sure, here is your script:" or sign-offs.
   - Output purely the clean, punctuated spoken text.`;

  return {
    prompt,
    targetLangCode: langInfo.code,
    targetLangName: langInfo.name,
    voiceName,
  };
}

/**
 * Call Gemini REST API (gemini-1.5-flash) to rewrite script according to selected voice language and presentation style.
 */
export async function optimizeScriptWithGemini(
  script: string,
  styleId: string,
  targetVoice?: TtsVoice | null,
  customApiKey?: string
): Promise<OptimizationResult> {
  const trimmed = script.trim();
  if (!trimmed) {
    throw new Error("Kịch bản đang trống. Vui lòng nhập nội dung kịch bản trước khi tối ưu.");
  }

  const style = PRESENTATION_STYLES.find((s) => s.id === styleId) || PRESENTATION_STYLES[0];
  const apiKey = (customApiKey || getStoredGeminiKey()).trim();
  const { prompt: systemPrompt, targetLangCode, targetLangName, voiceName } =
    buildSystemInstruction(style.id, targetVoice);

  const wordsOriginal = trimmed.split(/\s+/).length;
  const secOriginal = Math.round((wordsOriginal / 140) * 60);

  // If user provided an API Key, call official Google Gemini endpoint
  if (apiKey) {
    try {
      let activeModel = getStoredGeminiModel() || "gemini-2.5-flash";

      const payload = {
        contents: [
          {
            role: "user",
            parts: [
              {
                text: `Dưới đây là nội dung kịch bản sơ thảo của người dùng:\n\n"""\n${trimmed}\n"""\n\nHãy tối ưu hóa, chuyển thể sang đúng ngôn ngữ đích "${targetLangName}" và viết lại thành lời thoại hoàn chỉnh cho giọng "${voiceName}" theo phong cách "${style.name} (${style.vietnameseTitle})".`,
              },
            ],
          },
        ],
        systemInstruction: {
          parts: [
            {
              text: systemPrompt,
            },
          ],
        },
        generationConfig: {
          temperature: 0.65,
          topP: 0.95,
          maxOutputTokens: 2048,
        },
      };

      const sendRequest = async (model: string) => {
        const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
        return fetch(endpoint, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });
      };

      let resp = await sendRequest(activeModel);

      // If model not found (404) or unsupported, automatically discover available models and retry
      if (!resp.ok) {
        const errJson = await resp.clone().json().catch(() => null);
        const errMsg = errJson?.error?.message || "";
        if (
          resp.status === 404 ||
          errMsg.includes("not found") ||
          errMsg.includes("not supported") ||
          errMsg.includes("ListModels")
        ) {
          console.warn(`Model "${activeModel}" không khả dụng. Đang tự động dò tìm model mới từ Google API...`);
          const bestModel = await getBestAvailableGeminiModel(apiKey);
          if (bestModel && bestModel !== activeModel) {
            console.log(`Đã chuyển sang model hoạt động: ${bestModel}`);
            activeModel = bestModel;
            setStoredGeminiModel(bestModel);
            resp = await sendRequest(bestModel);
          }
        }
      }

      if (!resp.ok) {
        const errJson = await resp.json().catch(() => null);
        const errMsg = errJson?.error?.message || `HTTP ${resp.status} ${resp.statusText}`;
        throw new Error(`Google Gemini API báo lỗi: ${errMsg}`);
      }

      const data = await resp.json();
      const candidateText =
        data?.candidates?.[0]?.content?.parts?.[0]?.text?.trim() || "";

      if (candidateText) {
        // Strip markdown backticks if Gemini wrapped it in ```
        const cleanedText = candidateText
          .replace(/^```[\w]*\n/, "")
          .replace(/\n```$/, "")
          .trim();

        const wordsOpt = cleanedText.split(/\s+/).length;
        const secOpt = Math.round((wordsOpt / 140) * 60);

        return {
          originalScript: trimmed,
          optimizedScript: cleanedText,
          styleId: style.id,
          styleName: style.vietnameseTitle,
          source: "gemini_api",
          tokensUsed: data?.usageMetadata?.totalTokenCount,
          wordCountOriginal: wordsOriginal,
          wordCountOptimized: wordsOpt,
          estimatedSecOriginal: secOriginal,
          estimatedSecOptimized: secOpt,
          targetLanguage: targetLangCode,
          targetLanguageName: targetLangName,
          voiceName: voiceName,
          modelUsed: activeModel,
        };
      }
    } catch (apiErr: any) {
      console.warn("Gemini API call failed, offering fallback:", apiErr);
      throw apiErr;
    }
  }

  // Fallback: Intelligent offline style transformation if no API key is set yet
  const offlineOptimized = transformScriptOffline(trimmed, style.id, targetLangCode);
  const wordsOpt = offlineOptimized.split(/\s+/).length;
  const secOpt = Math.round((wordsOpt / 140) * 60);

  return {
    originalScript: trimmed,
    optimizedScript: offlineOptimized,
    styleId: style.id,
    styleName: style.vietnameseTitle,
    source: "offline_template",
    wordCountOriginal: wordsOriginal,
    wordCountOptimized: wordsOpt,
    estimatedSecOriginal: secOriginal,
    estimatedSecOptimized: secOpt,
    targetLanguage: targetLangCode,
    targetLanguageName: targetLangName,
    voiceName: voiceName,
  };
}

/**
 * Intelligent rule-based transformer when no Gemini API key is configured.
 * Automatically uses English templates when target voice is English, and Vietnamese for Vietnamese.
 */
function transformScriptOffline(raw: string, styleId: string, langCode: string): string {
  const clean = raw.trim();

  // English voice templates
  if (langCode === "en") {
    switch (styleId) {
      case "news_anchor":
        return `Good evening, this is the prime news briefing. ${clean} Stay tuned for further developments as this story continues to unfold.`;
      case "educational_explainer":
        return `Welcome back to today's masterclass. To understand this concept thoroughly, let's break it down: ${clean} I hope this breakdown helps you apply it immediately!`;
      case "cinematic_storytelling":
        return `In the quiet stillness of the moment, when the world fades into the background... ${clean} It reminds us that every journey holds profound meaning.`;
      case "documentary_narrator":
        return `Through the sweeping arc of time and human history, the record speaks with clarity: ${clean} These milestones stand as enduring testimony for generations to come.`;
      case "podcast_host":
        return `Hey everyone! Today I want to talk about something really interesting that caught my eye: ${clean} What are your thoughts on this? Let me know in the comments!`;
      case "product_showcase":
        return `Are you looking for a game-changing solution to supercharge your workflow? ${clean} Experience the next generation of creative studio tools today and claim your advantage!`;
      case "motivational_speaker":
        return `Do not wait another second! The greatest moment to redefine your path is right now: ${clean} Step up, take action, and claim your victory today!`;
      case "corporate_briefing":
        return `Good morning, executive committee. Here is the operational summary of key performance indicators: ${clean} Strategic execution milestones will roll out across all divisions as scheduled.`;
      case "social_creator":
        return `Stop scrolling right now if you do not want to miss this! ${clean} Double tap and save this video so you do not forget!`;
      case "calm_mindful":
        return `Take a slow, deep breath in... and let go of all the tension in your body... ${clean} May you find peace, clarity, and ease in every moment.`;
      default:
        return clean;
    }
  }

  // Vietnamese voice templates
  switch (styleId) {
    case "news_anchor":
      return `Kính chào quý vị và các bạn. Đây là thông tin cập nhật trọng điểm hôm nay. ${clean} Bản tin của chúng tôi sẽ tiếp tục cập nhật những diễn biến mới nhất trong các chuyên mục tiếp theo.`;
    case "educational_explainer":
      return `Chào mừng các bạn quay trở lại với bài chia sẻ kiến thức hôm nay. Để nắm bắt trọn vẹn chủ đề này, chúng ta cần lưu ý các trọng tâm: ${clean} Hy vọng những giải thích trên giúp bạn dễ dàng áp dụng vào thực tế!`;
    case "cinematic_storytelling":
      return `Trong một không gian tĩnh lặng, khi mọi chuyển động thường nhật dần lắng xuống... ${clean} Câu chuyện này nhắc nhớ chúng ta rằng, mỗi hành trình đều mang trong mình những giá trị vô giá.`;
    case "documentary_narrator":
      return `Theo dòng chảy của thời gian và lịch sử, những dấu ấn rõ nét nhất đã được ghi nhận: ${clean} Những dữ liệu này tiếp tục là minh chứng sâu sắc cho các thế hệ mai sau.`;
    case "podcast_host":
      return `Chào mọi người nha! Hôm nay mình ngồi đây muốn tâm sự với các bạn một chuyện rất thú vị: ${clean} Các bạn nghĩ sao về điều này? Hãy để lại suy nghĩ của mình nhé!`;
    case "product_showcase":
      return `Bạn đang tìm kiếm giải pháp đột phá để nâng tầm năng suất? ${clean} Hãy trải nghiệm giải pháp thế hệ mới ngay hôm nay để nhận ưu đãi đặc biệt!`;
    case "motivational_speaker":
      return `Đừng chần chừ thêm một giây phút nào nữa! Cơ hội tốt nhất để bạn bứt phá chính là ngay bây giờ: ${clean} Hãy đứng lên và hành động ngay hôm nay!`;
    case "corporate_briefing":
      return `Kính thưa ban lãnh đạo. Chúng tôi xin báo cáo tóm tắt các chỉ số vận hành trọng yếu: ${clean} Kế hoạch hành động cụ thể cho giai đoạn tới sẽ được triển khai đồng bộ.`;
    case "social_creator":
      return `Dừng lại 3 giây nếu bạn không muốn bỏ lỡ điều này! ${clean} Thả tim và lưu video ngay để không quên nhé!`;
    case "calm_mindful":
      return `Hãy hít một hơi thật sâu... và thả lỏng toàn bộ cơ thể... ${clean} Chúc bạn luôn tìm thấy sự an yên và thanh thản trong từng khoảnh khắc.`;
    default:
      return clean;
  }
}
