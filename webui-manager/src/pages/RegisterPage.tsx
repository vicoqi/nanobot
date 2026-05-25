import { useNavigate } from "react-router-dom";
import { register } from "@/lib/api";
import AuthForm from "@/components/AuthForm";

export default function RegisterPage() {
  const navigate = useNavigate();

  return (
    <AuthForm
      titleKey="auth.register"
      submitKey="auth.register"
      footerTextKey="auth.hasAccount"
      footerLinkKey="auth.login"
      footerHref="/login"
      errorFallbackKey="auth.registerFailed"
      onSubmit={register}
      onSuccess={() => navigate("/dashboard")}
    />
  );
}
