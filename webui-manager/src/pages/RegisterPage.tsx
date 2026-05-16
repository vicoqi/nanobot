import { useNavigate } from "react-router-dom";
import { register } from "@/lib/api";
import AuthForm from "@/components/AuthForm";

export default function RegisterPage() {
  const navigate = useNavigate();

  return (
    <AuthForm
      title="Register"
      submitLabel="Register"
      footerText="Already have an account?"
      footerLink="Login"
      footerHref="/login"
      errorFallback="Registration failed"
      onSubmit={register}
      onSuccess={() => navigate("/dashboard")}
    />
  );
}
