import { useState } from "react";
import { Link } from "react-router-dom";
import type { TokenResponse } from "@/lib/api";
import { setToken } from "@/lib/auth";
import { useI18n } from "@/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface AuthFormProps {
  titleKey: string;
  submitKey: string;
  footerTextKey: string;
  footerLinkKey: string;
  footerHref: string;
  errorFallbackKey: string;
  onSubmit: (username: string, password: string) => Promise<TokenResponse>;
  onSuccess: () => void;
}

export default function AuthForm({
  titleKey,
  submitKey,
  footerTextKey,
  footerLinkKey,
  footerHref,
  errorFallbackKey,
  onSubmit,
  onSuccess,
}: AuthFormProps) {
  const { t, locale, setLocale } = useI18n();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const { token } = await onSubmit(username, password);
      setToken(token);
      onSuccess();
    } catch (err: any) {
      setError(err.message || t(errorFallbackKey));
    }
  }

  return (
    <div className="relative flex min-h-dvh items-center justify-center p-4">
      <div className="absolute top-4 right-4">
        <Button variant="ghost" size="sm" onClick={() => setLocale(locale === "zh" ? "en" : "zh")}>
          {locale === "zh" ? "English" : "中文"}
        </Button>
      </div>
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4 p-6">
        <h1 className="text-2xl font-bold text-center">{t(titleKey)}</h1>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Input placeholder={t("auth.username")} value={username} onChange={(e) => setUsername(e.target.value)} required />
        <Input
          type="password"
          placeholder={t("auth.password")}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <Button type="submit" className="w-full">
          {t(submitKey)}
        </Button>
        <p className="text-center text-sm text-muted-foreground">
          {t(footerTextKey)}{" "}
          <Link to={footerHref} className="text-primary underline">
            {t(footerLinkKey)}
          </Link>
        </p>
      </form>
    </div>
  );
}
