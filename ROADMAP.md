# Future Roadmap 🛣️

Now that the core Voice Agent is stable, tested, and database-backed, here are the recommended next steps for Production.

## Phase 1: Deployment (Get off Localhost)
- [ ] **Dockerize**: Create a `Dockerfile` for the FastAPI server to ensure consistent environments.
- [ ] **Cloud Host**: Deploy the server to a cloud provider like **Render**, **Railway**, or **Google Cloud Run**.
- [ ] **Domain**: Purchase a domain and set up HTTPS (replaces `ngrok`).

## Phase 2: Observability & Monitoring
- [ ] **Logging**: Integrate a logging service (e.g., **Sentry**, **Datadog**) to track errors in real-time.
- [ ] **Dashboard**: Build a simple Admin UI (Streamlit/React) to view:
    -   Active Calls
    -   Open Tickets (from Redis)
    -   System Health

## Phase 3: Advanced Features
- [ ] **Proactive Calling**: When an outage is marked "Resolved" in Redis, automatically call affected users to let them know.
- [ ] **Secure Auth**: Implement OTP verification via SMS if the user requests sensitive data (don't just trust Caller ID).
- [ ] **RAG Integration**: Connect the "Tech Support Agent" to a vector database of PDF manuals to answer complex technical questions.

## Phase 4: Analytics
- [ ] **Call Analytics**: Track average call duration, sentiment analysis of user voice, and resolution rate.
