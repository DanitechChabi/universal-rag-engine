import { useAuth } from "../auth";

export function Assistant() {
  const { me } = useAuth();
  return (
    <div className="page">
      <h1>Bonjour {me?.display_name}</h1>
    </div>
  );
}
