using Workerd = import "/workerd/workerd.capnp";

const config :Workerd.Config = (
  services = [
    (name = "main", worker = .worker),
  ],
  sockets = [
    (service = "main", name = "http", address = "*:8080", http = ()),
  ],
);

const worker :Workerd.Worker = (
  modules = [
    (name = "worker", esModule = embed "dist/index.js"),
  ],
  # Match the compatibility_date in wrangler.toml
  compatibilityDate = "2024-10-22",
  # Match the compatibility flags in wrangler.toml
  compatibilityFlags = ["nodejs_compat", "cache_option_enabled"],
);
