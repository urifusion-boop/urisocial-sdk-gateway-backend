# Google OAuth Setup Guide for URI Social SDK Gateway

## Production Domain: https://developers.urisocial.com

Follow these steps to configure Google OAuth authentication for the SDK Gateway.

---

## 1. Google Cloud Console Setup

### Create OAuth 2.0 Credentials

1. **Go to Google Cloud Console**: https://console.cloud.google.com/
2. **Create/Select Project**: `URI Social SDK`
3. **Enable APIs**:
   - Go to "APIs & Services" → "Library"
   - Enable "Google+ API" or "Google Identity Services API"

### Configure OAuth Consent Screen

1. Go to **"APIs & Services"** → **"OAuth consent screen"**
2. Select **"External"** user type
3. Fill in the form:

```
App name: URI Social SDK Gateway
User support email: urisocialinsight@gmail.com
App logo: [Upload your logo]

Application home page: https://developers.urisocial.com
Application privacy policy: https://developers.urisocial.com/privacy
Application terms of service: https://developers.urisocial.com/terms

Authorized domains: urisocial.com

Developer contact email: urisocialinsight@gmail.com
```

4. **Add Scopes**:
   - `../auth/userinfo.email`
   - `../auth/userinfo.profile`
   - `openid`

5. **Publish App** (for production access)

### Create OAuth 2.0 Client ID

1. Go to **"APIs & Services"** → **"Credentials"**
2. Click **"Create Credentials"** → **"OAuth 2.0 Client ID"**
3. Configure:

```
Application type: Web application
Name: URI Social SDK Gateway

Authorized JavaScript origins:
- https://developers.urisocial.com
- http://localhost:3000 (for local testing)

Authorized redirect URIs:
- https://developers.urisocial.com/api/auth/google/callback
- http://localhost:8000/api/v1/auth/google/callback (for local testing)
```

4. **Copy the credentials**:
   - Client ID: `xxxxx.apps.googleusercontent.com`
   - Client Secret: `GOCSPX-xxxxx`

---

## 2. Backend Configuration

### Update `.env` file in `uri-social-gateway-backend`:

```env
# MongoDB Database
MONGODB_URL=your-mongodb-url
DATABASE_NAME=uri_gateway_prod

# JWT
SECRET_KEY=your-super-secret-key-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Redis
REDIS_URL=redis://your-redis-host:6379

# CORS
FRONTEND_URL=https://developers.urisocial.com

# Environment
ENVIRONMENT=production

# Email/SMTP
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USERNAME=urisocialinsight@gmail.com
SMTP_PASSWORD=your-smtp-app-password
SMTP_FROM_EMAIL=urisocialinsight@gmail.com
SMTP_FROM_NAME=URI Social SDK

# Google OAuth
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=https://developers.urisocial.com/api/auth/google/callback
```

---

## 3. Frontend Configuration

### Update `.env.production` in `urisocial-sdk-gateway`:

```env
NEXT_PUBLIC_API_URL=https://developers.urisocial.com/api
```

---

## 4. Local Development Setup

For local testing, create `.env.local` files:

### Backend `.env`:
```env
FRONTEND_URL=http://localhost:3000
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
```

### Frontend `.env.local`:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

And add these to Google Console:
- Origin: `http://localhost:3000`
- Redirect: `http://localhost:8000/api/v1/auth/google/callback`

---

## 5. How OAuth Flow Works

1. User clicks "Continue with Google" button
2. Frontend redirects to: `https://developers.urisocial.com/api/auth/google`
3. Backend redirects user to Google OAuth consent screen
4. User authorizes the app
5. Google redirects back to: `https://developers.urisocial.com/api/auth/google/callback`
6. Backend:
   - Exchanges code for Google user info
   - Creates or updates user account
   - Sets HttpOnly authentication cookies
   - Redirects to: `https://developers.urisocial.com/dashboard`
7. User is now logged in!

---

## 6. API Endpoints

### Initiate Google OAuth:
```
GET /api/v1/auth/google
```

### OAuth Callback (handled automatically by Google):
```
GET /api/v1/auth/google/callback
```

### Get Current User:
```
GET /api/v1/auth/me
```

---

## 7. Testing

1. **Install dependencies**:
```bash
cd uri-social-gateway-backend
pip install -r requirements.txt
```

2. **Run backend**:
```bash
uvicorn app.main:app --reload
```

3. **Run frontend**:
```bash
cd urisocial-sdk-gateway
npm run dev
```

4. **Test OAuth flow**:
   - Go to `http://localhost:3000/login`
   - Click "Continue with Google"
   - Authorize with Google
   - Should redirect to `/dashboard` after success

---

## 8. Deployment Checklist

- [ ] Google OAuth credentials created
- [ ] Authorized domains added to Google Console
- [ ] Redirect URIs configured correctly
- [ ] Backend `.env` configured with Google credentials
- [ ] Frontend `.env.production` configured
- [ ] App published in Google Console (for public access)
- [ ] Domain verified (if required)
- [ ] HTTPS enabled on production domain
- [ ] Cookies working across domain (same domain for frontend/backend API)

---

## 9. Troubleshooting

### "redirect_uri_mismatch" error:
- Check that the redirect URI in Google Console exactly matches your backend setting
- Ensure no trailing slashes
- Check http vs https

### "Origin not allowed":
- Add your domain to "Authorized JavaScript origins" in Google Console

### Cookies not being set:
- Ensure `FRONTEND_URL` matches your actual frontend domain
- Check CORS settings in backend
- Verify secure cookie settings for production

### "App not verified" warning:
- Add users to test list in Google Console
- Or publish app for public access

---

## Security Notes

1. **Never commit** `.env` files to git
2. Use **different OAuth credentials** for dev/staging/production
3. Keep `SECRET_KEY` secure and random (min 32 characters)
4. Use **HTTPS** in production
5. Regularly rotate OAuth client secrets
6. Monitor OAuth usage in Google Console
