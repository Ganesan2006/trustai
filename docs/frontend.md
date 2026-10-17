# Frontend

## Overview

The client is a same-origin, server-served interface built with HTML, CSS, and browser JavaScript. There is no `package.json`, bundler, or frontend compilation step. FastAPI serves page HTML from `client/pages/` and mounts `client/components/` at `/static`.

```text
client/
├── pages/
│   ├── login.html
│   ├── org_login.html
│   ├── chat.html
│   ├── admin.html
│   └── admin_dashboard.html
└── components/
    ├── auth/       # login.js/css, org_login.js/css
    ├── chat/       # chat.js/css
    └── admin/      # admin.js/css, admin_dashboard.js/css
```

The page routes are implemented in `server/app/api/v1/pages.py`; the static mount is configured in `server/app/main.py`. Keep HTML references such as `/static/chat/chat.js` aligned with the component paths when moving or renaming assets.

## Pages and responsibilities

| Page | URL | Main behavior and assets |
|---|---|---|
| `login.html` | `/` | Employee login and signup UI; `components/auth/login.js` calls login, signup, and organization department lookup endpoints. |
| `chat.html` | `/start`, `/chat/{conversation_id}` | Main chat, conversation navigation, document upload and selection, search scope, citations, feedback, profile and theme controls; uses `components/chat/chat.js`. |
| `org_login.html` | `/org/register` | Organization registration form and first administrator setup; uses `components/auth/org_login.js`. |
| `admin.html` | `/admin` | Organization management for users, departments, teams, API keys, model assignments, and uploaded files; uses `components/admin/admin.js`. |
| `admin_dashboard.html` | `/admin/dashboard` | Analytics views for usage, retrieval, documents, feedback, security, knowledge gaps, and organization details; uses `components/admin/admin_dashboard.js`. |

The chat page uses external browser libraries for Markdown rendering/sanitization and icons/fonts; the admin pages use Axios, and the analytics page uses Chart.js. These assets are loaded by the HTML documents from CDNs. The application-specific HTML/CSS/JavaScript remains in the repository.

## Authentication and browser state

On successful login/signup, the auth scripts store `access_token` and a serialized `user` in `localStorage`, then navigate to `/start`. Chat and admin scripts send the token in the `Authorization: Bearer ...` header. The chat script clears browser storage and returns to `/` on a 401 response. Logout clears `localStorage`.

The theme is stored as `trustai_theme`. The chat UI also stores each conversation's search-scope selection under a `chat_scope_<conversation-id>` key. This is UI convenience state; authorization and access filters are enforced by the server and must never trust values only because they came from local storage.

## API interaction patterns

- Auth forms use `fetch` for `/api/auth/...` requests.
- Chat and management flows use Axios for JSON endpoints. Chat generation uses `fetch` directly, then reads the JSON response containing the answer, citations, and query-log identifier.
- File uploads use multipart `FormData` at `/api/files/upload`.
- File viewing/download actions call the protected file endpoints; the current browser code may place the token in a query parameter for navigation to a file URL.
- Analytics tabs request data from `/admin/analytics/...` and render summary cards, tables, and Chart.js visualizations.

The UI should treat backend role checks and ownership rules as authoritative. Hiding a button or tab improves navigation but does not secure the associated API operation.

## Adding or changing UI features

1. Identify the page that owns the interaction and its existing component directory.
2. Add page-specific JavaScript and styles under `client/components/<feature>/` instead of embedding growing behavior in page markup.
3. Reference assets through `/static/<feature>/<file>` and verify that the static mount continues to serve that directory.
4. Call the existing same-origin API and use its established bearer-token pattern for protected requests. Send file content as `FormData` where the endpoint expects multipart data.
5. Add or update the API route in `server/app/api/v1/` and document its authorization and payload in [backend.md](backend.md).
6. Update this guide if the page map, browser state, shared assets, or UI dependencies change.

## Accessibility and maintenance notes

Keep form labels, button names, focus behavior, and error feedback understandable when changing HTML interactions. Escape user- or server-provided text before inserting it as HTML, and sanitize rendered Markdown using the existing client-side sanitization flow. Avoid putting credentials or private document content into persistent browser storage. There is no frontend test/build configuration in the repository; browser-specific changes should be reviewed against the actual pages and API contracts.
