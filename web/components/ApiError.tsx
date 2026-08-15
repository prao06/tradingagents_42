import { API_BASE } from "@/lib/api";

export default function ApiError({ error }: { error: string }) {
  return (
    <div className="error">
      Couldn’t reach the API ({error}).
      <br />
      <span className="muted">
        Backend: {API_BASE} — is it running, and is NEXT_PUBLIC_API_URL set?
      </span>
    </div>
  );
}
