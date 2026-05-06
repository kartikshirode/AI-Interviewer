import type { NextConfig } from "next";

const securityHeaders = [
  // Disallow framing the app from other origins (clickjacking).
  { key: "X-Frame-Options", value: "DENY" },
  // Don't let the browser sniff a different MIME type than the server sent.
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Conservative referrer policy.
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // Disable powerful APIs we don't use.
  {
    key: "Permissions-Policy",
    value: "geolocation=(), payment=(), usb=()",
  },
  // Force HTTPS for a year (only effective on HTTPS responses).
  {
    key: "Strict-Transport-Security",
    value: "max-age=31536000; includeSubDomains",
  },
  // Cross-origin isolation hardening — useful even without SAB usage.
  { key: "X-DNS-Prefetch-Control", value: "off" },
];

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
