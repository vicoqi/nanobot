import { useNavigate } from "react-router-dom";
import { login } from "@/lib/api";
import AuthForm from "@/components/AuthForm";

export default function LoginPage() {
  const navigate = useNavigate();

  return (
    <AuthForm
      title="Login"
      submitLabel="Login"
      footerText="No account?"
      footerLink="Register"
      footerHref="/register"
      errorFallback="Login failed"
      onSubmit={login}
      onSuccess={() => navigate("/dashboard")}
    />
  );
}
