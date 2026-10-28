# Free hosting guide

## 1. Backend on Hugging Face Spaces (free)
1. Create a free account at huggingface.co and a **write** token (Settings, Access Tokens).
2. In a terminal inside this project (with the `data` and `storage` folders present):
   ```
   pip install huggingface_hub
   set HF_TOKEN=hf_your_token
   python scripts/deploy_hf_space.py --space YOUR_USERNAME/alpha-discovery-api
   ```
3. Wait for the Space build. The API address is `https://YOUR_USERNAME-alpha-discovery-api.hf.space`.

## 2. Website on Cloudflare Pages (free)
1. Cloudflare dashboard, Workers and Pages, Create, Pages, Connect to Git, choose this repository.
2. Root directory `Alpha-Discovery-Multi-Agent`, build command `npm run build`, output directory `dist`.
3. Environment variables: `VITE_API_BASE_URL` = the Space address above, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.
4. `public/_redirects` already makes page addresses such as `/contact` work after a refresh.

## 3. Sign-in (Supabase) and Google
1. Supabase, SQL editor: run `supabase/schema.sql`.
2. Authentication, URL configuration: add your Cloudflare site address as the Site URL and a redirect URL.
3. Google: Google Cloud Console, create an OAuth client (Web). Authorized redirect URI is the callback shown in Supabase under Authentication, Providers, Google. Paste client ID and secret in Supabase and enable the provider.
