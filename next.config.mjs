/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // WebLLM's WASM runtime uses SharedArrayBuffer for multi-threaded decoding,
  // which browsers only expose on a "cross-origin isolated" page. This is the
  // header pair WebLLM's own examples use to get that isolation. It only
  // restricts embedded sub-resources (scripts, workers, iframes) — it does
  // NOT block plain fetch() calls, so it doesn't interfere with the model
  // weight downloads themselves.
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
          { key: "Cross-Origin-Embedder-Policy", value: "require-corp" },
        ],
      },
    ];
  },
  webpack: (config) => {
    config.resolve.fallback = { ...config.resolve.fallback, fs: false };
    return config;
  },
};

export default nextConfig;
