export function ErrorNotice({
  title,
  message,
}: {
  title?: string;
  message: string;
}) {
  return (
    <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
      {title ? <p className="font-medium">{title}</p> : null}
      <p
        className={[
          "whitespace-pre-wrap break-words",
          title ? "mt-1 text-red-200/90" : "",
        ].join(" ")}
      >
        {message}
      </p>
    </div>
  );
}
