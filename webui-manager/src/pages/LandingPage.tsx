import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useI18n } from "@/i18n";
import { isLoggedIn } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import {
  MessageSquare,
  Clock,
  Brain,
  Users,
  ImageIcon,
  Sparkles,
  Globe,
  UserPlus,
  QrCode,
  Send,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/* Feature card definitions (icon + i18n key)                         */
/* ------------------------------------------------------------------ */
const FEATURES = [
  { icon: MessageSquare, key: "chat" },
  { icon: Clock, key: "push" },
  { icon: Brain, key: "memory" },
  { icon: Users, key: "multiAgent" },
  { icon: ImageIcon, key: "image" },
  { icon: Sparkles, key: "noCode" },
] as const;

const STEPS = [
  { icon: UserPlus, key: "step1" },
  { icon: QrCode, key: "step2" },
  { icon: Send, key: "step3" },
] as const;

/* ------------------------------------------------------------------ */
/* WeChat Chat Bubble Mockup                                          */
/* ------------------------------------------------------------------ */
function WeChatMockup({ t }: { t: (k: string) => string }) {
  return (
    <div className="w-full max-w-[300px] rounded-2xl border shadow-xl overflow-hidden bg-[#EDEDED]">
      {/* Title bar */}
      <div className="bg-[#EDEDED] px-4 py-3 flex items-center gap-2 border-b border-black/5">
        <div className="w-7 h-7 rounded-full bg-[#07C160] flex items-center justify-center text-white text-xs font-bold">
          AI
        </div>
        <span className="text-sm font-medium text-gray-900">
          {t("landing.hero.chat.botName")}
        </span>
      </div>

      {/* Messages */}
      <div className="px-3 py-4 space-y-3 bg-[#EDEDED] min-h-[220px]">
        {/* User message (right, green) */}
        <div className="flex justify-end">
          <div className="bg-[#95EC69] rounded-lg px-3 py-2 max-w-[200px] text-sm text-gray-900 shadow-sm">
            {t("landing.hero.chat.user1")}
          </div>
        </div>

        {/* Bot message (left, white) */}
        <div className="flex justify-start gap-2">
          <div className="w-7 h-7 rounded-full bg-[#07C160] flex-shrink-0 flex items-center justify-center text-white text-xs font-bold">
            AI
          </div>
          <div className="bg-white rounded-lg px-3 py-2 max-w-[220px] text-sm text-gray-900 shadow-sm whitespace-pre-line">
            {t("landing.hero.chat.bot1")}
          </div>
        </div>

        {/* Second bot message */}
        <div className="flex justify-start gap-2">
          <div className="w-7 h-7 rounded-full bg-[#07C160] flex-shrink-0 flex items-center justify-center text-white text-xs font-bold">
            AI
          </div>
          <div className="bg-white rounded-lg px-3 py-2 max-w-[220px] text-sm text-gray-900 shadow-sm whitespace-pre-line">
            {t("landing.hero.chat.bot2")}
          </div>
        </div>
      </div>

      {/* Input bar */}
      <div className="bg-[#F7F7F7] px-3 py-2 border-t border-black/5 flex items-center gap-2">
        <div className="flex-1 bg-white rounded-md px-3 py-1.5 text-xs text-gray-400 border">
          {t("landing.hero.chat.input")}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Landing Page                                                       */
/* ------------------------------------------------------------------ */
export default function LandingPage() {
  const navigate = useNavigate();
  const { locale, setLocale, t } = useI18n();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    if (isLoggedIn()) {
      navigate("/dashboard", { replace: true });
    }
  }, [navigate]);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* ---- Navbar ---- */}
      <nav
        className={`fixed top-0 inset-x-0 z-50 transition-all duration-200 ${
          scrolled
            ? "bg-background/80 backdrop-blur-md border-b"
            : "bg-transparent"
        }`}
      >
        <div className="mx-auto max-w-6xl flex items-center justify-between px-4 py-3">
          <Link to="/" className="text-xl font-bold tracking-tight">
            {locale === "zh" ? "贾维斯特" : "Jarvis Agent"}
          </Link>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setLocale(locale === "zh" ? "en" : "zh")}
            >
              <Globe className="w-4 h-4 mr-1" />
              {locale === "zh" ? "EN" : "中文"}
            </Button>
            <Link to="/login">
              <Button variant="ghost" size="sm">
                {t("landing.nav.login")}
              </Button>
            </Link>
            <Link to="/register">
              <Button size="sm">{t("landing.nav.register")}</Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* ---- Hero ---- */}
      <section className="min-h-[90vh] flex items-center pt-16">
        <div className="mx-auto max-w-6xl px-4 py-20 flex flex-col lg:flex-row items-center gap-12 lg:gap-16">
          {/* Left: copy */}
          <div className="flex-1 text-center lg:text-left">
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-tight">
              {t("landing.hero.title")}
            </h1>
            <p className="mt-4 text-lg sm:text-xl text-muted-foreground max-w-xl mx-auto lg:mx-0">
              {t("landing.hero.subtitle")}
            </p>
            <div className="mt-8 flex flex-col sm:flex-row items-center gap-3 justify-center lg:justify-start">
              <Link to="/register">
                <Button size="lg" className="text-base px-8">
                  {t("landing.hero.cta")}
                </Button>
              </Link>
              <Link to="/login">
                <Button variant="outline" size="lg" className="text-base px-8">
                  {t("landing.hero.ctaSecondary")}
                </Button>
              </Link>
            </div>
          </div>

          {/* Right: WeChat mockup */}
          <div className="flex-shrink-0">
            <WeChatMockup t={t} />
          </div>
        </div>
      </section>

      {/* ---- Features ---- */}
      <section className="py-20 px-4">
        <div className="mx-auto max-w-6xl">
          <div className="text-center mb-12">
            <h2 className="text-3xl sm:text-4xl font-bold">
              {t("landing.features.title")}
            </h2>
            <p className="mt-3 text-muted-foreground text-lg">
              {t("landing.features.subtitle")}
            </p>
          </div>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, key }) => (
              <div
                key={key}
                className="rounded-lg border bg-card p-6 transition-shadow hover:shadow-md"
              >
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
                  <Icon className="w-5 h-5 text-primary" />
                </div>
                <h3 className="font-semibold text-lg mb-2">
                  {t(`landing.features.${key}.title`)}
                </h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {t(`landing.features.${key}.desc`)}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---- How It Works ---- */}
      <section className="py-20 px-4 bg-muted/30">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-3xl sm:text-4xl font-bold text-center mb-12">
            {t("landing.howItWorks.title")}
          </h2>
          <div className="grid gap-8 sm:grid-cols-3">
            {STEPS.map(({ icon: Icon, key }, i) => (
              <div key={key} className="text-center">
                <div className="mx-auto w-12 h-12 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-lg font-bold mb-4">
                  {i + 1}
                </div>
                <div className="mx-auto w-10 h-10 text-muted-foreground mb-3 flex items-center justify-center">
                  <Icon className="w-6 h-6" />
                </div>
                <h3 className="font-semibold text-lg mb-2">
                  {t(`landing.howItWorks.${key}.title`)}
                </h3>
                <p className="text-sm text-muted-foreground">
                  {t(`landing.howItWorks.${key}.desc`)}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---- Bottom CTA ---- */}
      <section className="py-20 px-4">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl sm:text-4xl font-bold">
            {t("landing.cta.title")}
          </h2>
          <p className="mt-3 text-muted-foreground text-lg">
            {t("landing.cta.subtitle")}
          </p>
          <div className="mt-8">
            <Link to="/register">
              <Button size="lg" className="text-base px-10">
                {t("landing.cta.button")}
              </Button>
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
