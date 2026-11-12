# Privacy Policy — MAREF YouTube Publisher

**Effective date:** 2026-11-12

## 1. What this application is

"MAREF YouTube Publisher" is the OAuth 2.0 client used by the MAREF project
(`maref-org/maref`) to publish video content to the YouTube channel operated by
the project owner. It is a self-hosted command-line tool; there is no public
service, server-side component, or user-facing website behind this OAuth client.

## 2. Google OAuth scopes and why they are requested

| Scope | Purpose |
|---|---|
| `https://www.googleapis.com/auth/youtube.upload` | Upload video files to the authenticated user's own YouTube channel. |
| `https://www.googleapis.com/auth/youtube.force-ssl` | Manage (schedule, update metadata of) the videos uploaded by this tool on the same channel. |

The application requests the minimum scopes required to upload and schedule
videos on the channel that performs the OAuth authorization. It does not
request access to any other Google service or to third-party accounts.

## 3. Data collected, stored, and shared

- **Personal data collected by the application: none.** The tool has no
  analytics, no telemetry, no advertising, and no server-side storage.
- **OAuth tokens** (access/refresh tokens) are stored **only on the local
  machine of the operator** who performed the authorization, in a
  git-ignored local file and/or the macOS Keychain. They are never
  transmitted anywhere other than Google's OAuth and YouTube Data API
  endpoints.
- **Uploaded content** (videos, titles, descriptions) is created and supplied
  by the operator of the channel. Once uploaded, the content is governed by
  YouTube's own terms and Google's privacy policy.

## 4. Data sharing with third parties

None. The application does not sell, rent, or share any data with third
parties.

## 5. Data retention and deletion

- Local OAuth tokens persist until the operator revokes them (Google Account
  → Security → Third-party apps with account access) or deletes the local
  token file.
- Uploaded videos remain on the operator's YouTube channel until the operator
  deletes them.

## 6. Limited Use compliance

The application's use of YouTube API Services data complies with the
YouTube API Services Terms of Service and Google's Limited Use requirements:
data is used solely to upload and manage the operator's own videos, is not
used for advertising or any other purpose, and is not aggregated with data
from other applications.

## 7. Contact

For any privacy questions regarding this OAuth client, contact:
**yangfrankie942@gmail.com**

## 8. Changes to this policy

If this policy changes, the updated version will be committed to this
repository with a revised effective date.
