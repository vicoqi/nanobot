import { useNavigate } from "react-router-dom";
import { login } from "@/lib/api";
import AuthForm from "@/components/AuthForm";

export default function LoginPage() {
  const navigate = useNavigate();

  return (
    <AuthForm
      titleKey="auth.login"
      submitKey="auth.login"
      footerTextKey="auth.noAccount"
      footerLinkKey="auth.register"
      footerHref="/register"
      errorFallbackKey="auth.loginFailed"
      onSubmit={login}
      onSuccess={() => navigate("/dashboard")}
    />
  );
}
