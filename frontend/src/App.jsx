import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { isSupabaseConfigured, supabase } from './supabaseClient'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

const starterMessage = {
  role: 'assistant',
  content:
    'Upload a document or pick an existing project. You can ask direct questions, request a summary, or ask for an explanation of the document.'
}

const quickPrompts = [
  'Explain the uploaded document in simple terms.',
  'Summarize the key findings from the uploaded document.',
  'What are the most important concepts or sections in this document?',
  'Compare the uploaded documents and highlight agreements and differences.',
  'Extract the key findings, risks, limitations, and action items from these documents.'
]

function createProjectKey() {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  const time = String(now.getTime()).slice(-5)
  return `project-${y}${m}${d}-${time}`
}

function App() {
  const [authReady, setAuthReady] = useState(false)
  const [session, setSession] = useState(null)
  const [authMode, setAuthMode] = useState('signin')
  const [authEmail, setAuthEmail] = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authError, setAuthError] = useState('')
  const [authNotice, setAuthNotice] = useState('')
  const [isAuthenticating, setIsAuthenticating] = useState(false)

  const [projectId, setProjectId] = useState(() => createProjectKey())
  const [projects, setProjects] = useState([])
  const [documents, setDocuments] = useState([])
  const [chats, setChats] = useState([])
  const [messages, setMessages] = useState([starterMessage])
  const [chatId, setChatId] = useState(null)
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [isLoadingWorkspace, setIsLoadingWorkspace] = useState(false)
  const [file, setFile] = useState(null)
  const [uploadStatus, setUploadStatus] = useState('No file uploaded yet.')
  const [uploadProgress, setUploadProgress] = useState(null)
  const [arxivQuery, setArxivQuery] = useState('')
  const [arxivResults, setArxivResults] = useState([])
  const [arxivStatus, setArxivStatus] = useState('')
  const [isSearchingArxiv, setIsSearchingArxiv] = useState(false)
  const [isFindingRelatedArxiv, setIsFindingRelatedArxiv] = useState(false)
  const [importingArxivId, setImportingArxivId] = useState(null)
  const [workspaceTab, setWorkspaceTab] = useState('documents')
  const bottomRef = useRef(null)

  const canSend = useMemo(() => input.trim().length > 0 && !isSending, [input, isSending])
  const userEmail = session?.user?.email || ''

  useEffect(() => {
    if (!isSupabaseConfigured) {
      setAuthReady(true)
      return
    }

    let isMounted = true

    async function bootAuth() {
      const { data } = await supabase.auth.getSession()
      if (isMounted) {
        setSession(data.session)
        setAuthReady(true)
      }
    }

    bootAuth()

    const {
      data: { subscription }
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (!isMounted) {
        return
      }
      setSession(nextSession)
      setAuthReady(true)
    })

    return () => {
      isMounted = false
      subscription.unsubscribe()
    }
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isSending])

  useEffect(() => {
    if (!session) {
      setProjects([])
      setDocuments([])
      setChats([])
      setMessages([starterMessage])
      setChatId(null)
      setProjectId(createProjectKey())
      return
    }

    loadProjects()
  }, [session])

  useEffect(() => {
    if (!session) {
      return
    }

    if (!projectId.trim()) {
      setDocuments([])
      setChats([])
      setMessages([starterMessage])
      setChatId(null)
      return
    }

    loadWorkspace(projectId)
  }, [projectId, session])

  async function getAccessToken() {
    if (!supabase) {
      throw new Error('Supabase not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.')
    }

    const {
      data: { session: nextSession }
    } = await supabase.auth.getSession()

    if (!nextSession?.access_token) {
      throw new Error('You are not signed in.')
    }

    return nextSession.access_token
  }

  async function fetchJson(path, options = {}) {
    const token = await getAccessToken()
    const headers = new Headers(options.headers || {})

    if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }
    headers.set('Authorization', `Bearer ${token}`)

    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers
    })
    if (!response.ok) {
      const text = await response.text()
      throw new Error(text || `Request failed (${response.status})`)
    }
    return response.json()
  }

  async function handleAuthSubmit(event) {
    event.preventDefault()
    if (!supabase) {
      setAuthError('Supabase is not configured on the frontend.')
      return
    }

    setIsAuthenticating(true)
    setAuthError('')
    setAuthNotice('')

    try {
      if (authMode === 'signup') {
        const { data, error } = await supabase.auth.signUp({
          email: authEmail,
          password: authPassword
        })
        if (error) {
          throw error
        }
        if (data.session) {
          setAuthNotice('Account created and signed in.')
        } else {
          setAuthNotice('Account created. Check your email to confirm your sign-up before logging in.')
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword({
          email: authEmail,
          password: authPassword
        })
        if (error) {
          throw error
        }
      }
      setAuthPassword('')
    } catch (error) {
      setAuthError(error.message || 'Authentication failed.')
    } finally {
      setIsAuthenticating(false)
    }
  }

  async function handleSignOut() {
    if (!supabase) {
      return
    }
    await supabase.auth.signOut()
    setProjectId(createProjectKey())
    setAuthPassword('')
    setAuthNotice('')
    setAuthError('')
  }

  async function loadProjects() {
    try {
      const data = await fetchJson('/projects/')
      const nextProjects = Array.isArray(data?.projects) ? data.projects : []
      setProjects(nextProjects)

      if (nextProjects.length === 0) {
        setProjectId((current) => (current.trim() ? current : createProjectKey()))
        return
      }

      const hasCurrentProject = nextProjects.some((project) => project.project_key === projectId)
      if (!hasCurrentProject) {
        setProjectId(nextProjects[0].project_key)
      }
    } catch (error) {
      console.error('Failed to load projects', error)
    }
  }

  async function loadWorkspace(nextProjectId) {
    setIsLoadingWorkspace(true)
    try {
      const [documentsData, chatsData] = await Promise.all([
        fetchJson(`/documents/?project_id=${encodeURIComponent(nextProjectId)}`),
        fetchJson(`/chats/?project_id=${encodeURIComponent(nextProjectId)}`)
      ])

      const nextDocuments = Array.isArray(documentsData?.documents) ? documentsData.documents : []
      const nextChats = Array.isArray(chatsData?.chats) ? chatsData.chats : []
      setDocuments(nextDocuments)
      setChats(nextChats)

      if (nextChats.length === 0) {
        setChatId(null)
        setMessages([starterMessage])
        return
      }

      const keepCurrentChat = nextChats.some((chat) => chat.id === chatId)
      const latestChatId = keepCurrentChat ? chatId : nextChats[0].id
      setChatId(latestChatId)
      await loadMessages(latestChatId)
    } catch (error) {
      console.error('Failed to load workspace', error)
      setDocuments([])
      setChats([])
      setMessages([starterMessage])
      setChatId(null)
    } finally {
      setIsLoadingWorkspace(false)
    }
  }

  async function loadMessages(nextChatId) {
    const data = await fetchJson(`/messages/?chat_id=${nextChatId}`)
    const nextMessages = Array.isArray(data?.messages) ? data.messages : []
    setMessages(
      nextMessages.length > 0
        ? nextMessages.map((message) => ({
            role: message.role,
            content: message.content,
            sources: Array.isArray(message.sources) ? message.sources : []
          }))
        : [starterMessage]
    )
  }

  async function submitQuestion(question) {
    const trimmedQuestion = question.trim()
    if (!trimmedQuestion || isSending) {
      return
    }

    setInput('')
    setIsSending(true)
    setMessages((prev) => [...prev, { role: 'user', content: trimmedQuestion }])

    try {
      const data = await fetchJson('/query/', {
        method: 'POST',
        body: JSON.stringify({
          project_id: projectId,
          question: trimmedQuestion,
          chat_id: chatId
        })
      })

      const nextChatId = data?.chat_id ?? null
      if (nextChatId && chatId === null) {
        setChatId(nextChatId)
      }

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data?.answer ?? 'No answer returned.',
          sources: Array.isArray(data?.sources) ? data.sources : []
        }
      ])

      const chatsData = await fetchJson(`/chats/?project_id=${encodeURIComponent(projectId)}`)
      setChats(Array.isArray(chatsData?.chats) ? chatsData.chats : [])
      await loadProjects()
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Sorry, I could not reach the backend. ${error.message}`
        }
      ])
    } finally {
      setIsSending(false)
    }
  }

  function handleSend(event) {
    event.preventDefault()
    submitQuestion(input)
  }

  function handleQuickPrompt(prompt) {
    setWorkspaceTab('prompts')
    setInput(prompt)
    submitQuestion(prompt)
  }

  async function handleUpload() {
    if (!file) {
      setUploadStatus('Pick a file first.')
      return
    }

    setUploadProgress(0)
    setUploadStatus('Uploading...')

    const formData = new FormData()
    formData.append('file', file)
    formData.append('project_id', projectId)

    const token = await getAccessToken()
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}/upload/`)
    xhr.setRequestHeader('Authorization', `Bearer ${token}`)

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const percent = Math.round((event.loaded / event.total) * 100)
        setUploadProgress(percent)
        setUploadStatus(`Uploading ${percent}%`)
      }
    }

    xhr.onload = async () => {
      setUploadProgress(null)
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data = JSON.parse(xhr.responseText)
          setUploadStatus(`Uploaded and indexed: ${data.filename}`)
          setFile(null)
          await loadWorkspace(projectId)
          await loadProjects()
        } catch (_error) {
          setUploadStatus('Upload complete, but response parsing failed.')
        }
      } else {
        let detail = xhr.responseText
        try {
          const payload = JSON.parse(xhr.responseText)
          detail = payload?.detail || payload?.message || xhr.responseText
        } catch (_) {
          // Keep the raw response text when the backend did not return JSON.
        }
        setUploadStatus(detail ? `Upload failed (${xhr.status}): ${detail}` : `Upload failed (${xhr.status})`)
      }
    }

    xhr.onerror = () => {
      setUploadProgress(null)
      setUploadStatus('Upload error: network failure')
    }

    xhr.send(formData)
  }

  async function handleArxivSearch(event) {
    event.preventDefault()
    const query = arxivQuery.trim()
    if (!query) {
      setArxivStatus('Enter a topic or paper title.')
      return
    }

    setIsSearchingArxiv(true)
    setArxivStatus('Searching arXiv...')
    try {
      const data = await fetchJson(`/arxiv/search?query=${encodeURIComponent(query)}&max_results=6`)
      const papers = Array.isArray(data?.papers) ? data.papers : []
      setArxivResults(papers)
      setArxivStatus(papers.length ? `${papers.length} papers found.` : 'No papers found.')
    } catch (error) {
      setArxivStatus(`Search failed: ${error.message}`)
    } finally {
      setIsSearchingArxiv(false)
    }
  }

  async function handleRelatedArxivSearch() {
    if (!projectId.trim()) {
      setArxivStatus('Set a project ID first.')
      return
    }

    setIsFindingRelatedArxiv(true)
    setArxivStatus('Finding related arXiv papers...')
    try {
      const data = await fetchJson(`/arxiv/related?project_id=${encodeURIComponent(projectId)}&max_results=6`)
      const papers = Array.isArray(data?.papers) ? data.papers : []
      setArxivResults(papers)
      if (!data?.query) {
        setArxivStatus('Upload or import a document first.')
      } else {
        setArxivStatus(papers.length ? `Related papers found for: ${data.query}` : `No related papers found for: ${data.query}`)
      }
    } catch (error) {
      setArxivStatus(`Related search failed: ${error.message}`)
    } finally {
      setIsFindingRelatedArxiv(false)
    }
  }

  async function handleArxivImport(arxivId) {
    if (!projectId.trim()) {
      setArxivStatus('Set a project ID before importing.')
      return
    }

    setImportingArxivId(arxivId)
    setArxivStatus('Importing paper...')
    try {
      await fetchJson('/arxiv/import', {
        method: 'POST',
        body: JSON.stringify({ project_id: projectId, arxiv_id: arxivId })
      })
      setArxivStatus('Paper imported and indexed.')
      await loadWorkspace(projectId)
      await loadProjects()
    } catch (error) {
      setArxivStatus(`Import failed: ${error.message}`)
    } finally {
      setImportingArxivId(null)
    }
  }

  async function handleDeleteProject(event, nextProjectId) {
    event.stopPropagation()
    if (!window.confirm(`Delete project "${nextProjectId}" and its chats/documents?`)) {
      return
    }

    try {
      await fetchJson(`/projects/${encodeURIComponent(nextProjectId)}`, {
        method: 'DELETE'
      })
      const remainingProjects = projects.filter((project) => project.project_key !== nextProjectId)
      setProjects(remainingProjects)

      if (nextProjectId === projectId) {
        const fallbackProject = remainingProjects[0]?.project_key || createProjectKey()
        setProjectId(fallbackProject)
        if (!remainingProjects.length) {
          setDocuments([])
          setChats([])
          setMessages([starterMessage])
          setChatId(null)
        }
      }

      await loadProjects()
    } catch (error) {
      window.alert(`Could not delete project: ${error.message}`)
    }
  }

  async function handleDeleteDocument(documentId, title) {
    if (!window.confirm(`Delete "${title}" from this project?`)) {
      return
    }

    try {
      await fetchJson(`/documents/${documentId}`, {
        method: 'DELETE'
      })
      await loadWorkspace(projectId)
      await loadProjects()
    } catch (error) {
      window.alert(`Could not delete document: ${error.message}`)
    }
  }

  function onKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submitQuestion(input)
    }
  }

  function selectProject(nextProjectId) {
    setProjectId(nextProjectId)
  }

  function selectChat(nextChatId) {
    setChatId(nextChatId)
    loadMessages(nextChatId)
  }

  if (!authReady) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <p className="auth-eyebrow">RAG Assistant</p>
          <h1>Preparing workspace</h1>
          <p className="auth-copy">Checking your session and loading the research desk.</p>
        </div>
      </div>
    )
  }

  if (!isSupabaseConfigured) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <p className="auth-eyebrow">Supabase Required</p>
          <h1>Frontend auth is not configured</h1>
          <p className="auth-copy">
            Set <code>VITE_SUPABASE_URL</code> and <code>VITE_SUPABASE_ANON_KEY</code> in
            <code> frontend/.env</code>.
          </p>
        </div>
      </div>
    )
  }

  if (!session) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <p className="auth-eyebrow">Research Workspace</p>
          <h1>{authMode === 'signup' ? 'Create your account' : 'Sign in to continue'}</h1>
          <p className="auth-copy">
            Your projects, documents, and chat history will be isolated per user through Supabase Auth.
          </p>
          <form className="auth-form" onSubmit={handleAuthSubmit}>
            <input
              className="input"
              type="email"
              value={authEmail}
              onChange={(event) => setAuthEmail(event.target.value)}
              placeholder="Email"
              required
            />
            <input
              className="input"
              type="password"
              value={authPassword}
              onChange={(event) => setAuthPassword(event.target.value)}
              placeholder="Password"
              minLength={6}
              required
            />
            <button className="button auth-submit" type="submit" disabled={isAuthenticating}>
              {isAuthenticating ? 'Working...' : authMode === 'signup' ? 'Create account' : 'Sign in'}
            </button>
          </form>
          {authError ? <p className="auth-error">{authError}</p> : null}
          {authNotice ? <p className="auth-notice">{authNotice}</p> : null}
          <button
            className="auth-toggle"
            type="button"
            onClick={() => {
              setAuthMode((current) => (current === 'signup' ? 'signin' : 'signup'))
              setAuthError('')
              setAuthNotice('')
            }}
          >
            {authMode === 'signup' ? 'Already have an account? Sign in' : 'New here? Create an account'}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <aside className="project-rail">
        <div className="brand">
          <div className="brand-mark">R</div>
          <div>
            <p className="brand-title">RAG Assistant</p>
            <p className="brand-subtitle">Research workspace</p>
          </div>
        </div>

        <section className="rail-section account-card">
          <p className="label">Account</p>
          <p className="account-email">{userEmail}</p>
          <button className="secondary-button account-button" type="button" onClick={handleSignOut}>
            Sign out
          </button>
        </section>

        <section className="rail-section">
          <label className="label" htmlFor="project">
            Project
          </label>
          <input
            id="project"
            className="input"
            value={projectId}
            onChange={(event) => setProjectId(event.target.value)}
            placeholder="marketing-q1"
          />
        </section>

        <section className="rail-section rail-scroll">
          <div className="section-heading">
            <p className="label">Projects</p>
            <span>{projects.length}</span>
          </div>
          <div className="stack-list">
            {projects.length === 0 ? <p className="empty">No saved projects yet.</p> : null}
            {projects.map((project) => (
              <div
                key={project.id}
                className={`nav-row ${project.project_key === projectId ? 'active' : ''}`}
                role="button"
                tabIndex={0}
                onClick={() => selectProject(project.project_key)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    selectProject(project.project_key)
                  }
                }}
              >
                <span className="row-title">{project.project_key}</span>
                <span className="item-actions">
                  <small>{project.document_count} docs</small>
                  <button
                    className="icon-button danger"
                    type="button"
                    title="Delete project"
                    onClick={(event) => handleDeleteProject(event, project.project_key)}
                  >
                    x
                  </button>
                </span>
              </div>
            ))}
          </div>
        </section>

        <section className="rail-section rail-scroll">
          <div className="section-heading">
            <p className="label">Chats</p>
            <span>{chats.length}</span>
          </div>
          <div className="stack-list compact">
            {chats.length === 0 ? <p className="empty">No saved chats yet.</p> : null}
            {chats.map((chat) => (
              <button
                key={chat.id}
                className={`nav-row ${chat.id === chatId ? 'active' : ''}`}
                type="button"
                onClick={() => selectChat(chat.id)}
              >
                <span className="row-title">{chat.title || 'Untitled chat'}</span>
                <small>{new Date(chat.created_at).toLocaleDateString()}</small>
              </button>
            ))}
          </div>
        </section>
      </aside>

      <main className="chat-pane">
        <header className="chat-header">
          <div>
            <h1>Research Chat</h1>
            <p>
              {isLoadingWorkspace
                ? 'Loading project workspace...'
                : `${projectId || 'unset'} | ${documents.length} source(s)`}
            </p>
          </div>
          <div className="toolbar">
            <button className="toolbar-button" type="button" onClick={() => setWorkspaceTab('documents')}>
              Sources
            </button>
            <button className="toolbar-button" type="button" onClick={() => setWorkspaceTab('papers')}>
              Papers
            </button>
            <button className="toolbar-button" type="button" onClick={() => setWorkspaceTab('prompts')}>
              Prompts
            </button>
          </div>
        </header>

        <div className="messages">
          {messages.map((message, index) => (
            <div key={`${message.role}-${index}`} className={`message ${message.role}`}>
              <div className="avatar">{message.role === 'user' ? 'U' : 'A'}</div>
              <div className="bubble">
                {message.role === 'assistant' ? (
                  <ReactMarkdown
                    className="markdown-content"
                    remarkPlugins={[remarkGfm]}
                    components={{
                      a: ({ node, ...props }) => (
                        <a {...props} target="_blank" rel="noreferrer" />
                      )
                    }}
                  >
                    {message.content}
                  </ReactMarkdown>
                ) : (
                  <div className="plain-content">{message.content}</div>
                )}
                {message.role === 'assistant' && message.sources?.length ? (
                  <details className="sources-dropdown">
                    <summary className="sources-summary">Sources ({message.sources.length})</summary>
                    <div className="sources">
                      <div className="sources-list">
                        {message.sources.map((source, sourceIndex) => (
                          <div key={`${source.source}-${sourceIndex}`} className="source-card">
                            <div className="source-chip">
                              {source.source}
                              {source.page !== undefined && source.page !== null
                                ? ` (p.${source.page + 1})`
                                : ''}
                            </div>
                            {source.section_title ? (
                              <p className="source-section">{source.section_title}</p>
                            ) : null}
                            {source.excerpt ? <p className="source-excerpt">{source.excerpt}</p> : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  </details>
                ) : null}
              </div>
            </div>
          ))}
          {isSending ? (
            <div className="message assistant">
              <div className="avatar">A</div>
              <div className="bubble typing">Thinking...</div>
            </div>
          ) : null}
          <div ref={bottomRef} />
        </div>

        <form className="composer" onSubmit={handleSend}>
          <textarea
            className="textarea"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask a question, request a summary, or compare sources..."
            rows={2}
          />
          <button className="send" type="submit" disabled={!canSend || !projectId.trim()}>
            Send
          </button>
        </form>
      </main>

      <aside className="workspace-panel">
        <div className="workspace-tabs" role="tablist" aria-label="Workspace tools">
          {['documents', 'papers', 'prompts'].map((tab) => (
            <button
              key={tab}
              className={`tab-button ${workspaceTab === tab ? 'active' : ''}`}
              type="button"
              onClick={() => setWorkspaceTab(tab)}
            >
              {tab}
            </button>
          ))}
        </div>

        {workspaceTab === 'documents' ? (
          <div className="workspace-section">
            <div className="section-heading">
              <p className="label">Documents</p>
              <span>{documents.length}</span>
            </div>

            <div className="upload-zone">
              <input
                id="file"
                type="file"
                className="file"
                onChange={(event) => setFile(event.target.files?.[0] || null)}
              />
              <button className="button" type="button" onClick={handleUpload}>
                Upload and index
              </button>
              {uploadProgress !== null ? (
                <div className="progress">
                  <div className="progress-bar" style={{ width: `${uploadProgress}%` }} />
                </div>
              ) : null}
              <p className="status">{uploadStatus}</p>
            </div>

            <div className="source-list">
              {documents.length === 0 ? <p className="empty">No documents in this project yet.</p> : null}
              {documents.map((document) => (
                <div key={document.id} className="source-row">
                  <div>
                    <p className="source-row-title">{document.title || document.filename}</p>
                    <p className="source-row-meta">
                      {document.source_type || 'local'} | {new Date(document.uploaded_at).toLocaleDateString()}
                    </p>
                  </div>
                  <button
                    className="icon-button danger"
                    type="button"
                    title="Delete document"
                    onClick={() => handleDeleteDocument(document.id, document.title || document.filename)}
                  >
                    x
                  </button>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {workspaceTab === 'papers' ? (
          <div className="workspace-section">
            <p className="label">arXiv Papers</p>
            <form className="arxiv-search" onSubmit={handleArxivSearch}>
              <input
                className="input"
                value={arxivQuery}
                onChange={(event) => setArxivQuery(event.target.value)}
                placeholder="Search papers..."
              />
              <button className="button" type="submit" disabled={isSearchingArxiv}>
                Search
              </button>
            </form>
            <button
              className="secondary-button"
              type="button"
              onClick={handleRelatedArxivSearch}
              disabled={isFindingRelatedArxiv}
            >
              {isFindingRelatedArxiv ? 'Finding related papers...' : 'Find related papers'}
            </button>
            {arxivStatus ? <p className="status">{arxivStatus}</p> : null}
            <div className="arxiv-results">
              {arxivResults.map((paper) => (
                <div key={paper.arxiv_id} className="arxiv-card">
                  <div>
                    <p className="arxiv-title">{paper.title}</p>
                    <p className="arxiv-meta">
                      {paper.authors?.slice(0, 3).join(', ')}
                      {paper.authors?.length > 3 ? ' et al.' : ''}
                    </p>
                  </div>
                  <button
                    className="secondary-button compact-button"
                    type="button"
                    onClick={() => handleArxivImport(paper.arxiv_id)}
                    disabled={importingArxivId === paper.arxiv_id}
                  >
                    {importingArxivId === paper.arxiv_id ? 'Importing' : 'Import'}
                  </button>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {workspaceTab === 'prompts' ? (
          <div className="workspace-section">
            <p className="label">Prompt Ideas</p>
            <div className="quick-actions">
              {quickPrompts.map((prompt) => (
                <button
                  key={prompt}
                  className="secondary-button"
                  type="button"
                  onClick={() => handleQuickPrompt(prompt)}
                  disabled={isSending}
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </aside>
    </div>
  )
}

export default App
