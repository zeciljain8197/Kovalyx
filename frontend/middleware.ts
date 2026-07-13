import { NextRequest, NextResponse } from 'next/server'

/**
 * Protects /pipeline with HTTP Basic auth. Runs at the Edge, before the
 * page renders, so unauthenticated requests never reach the Server
 * Component that reads the audit schema via the service role key.
 *
 * Must live at frontend/middleware.ts (project root) — Next.js only
 * recognizes a middleware file there, not nested under app/.
 */
export function middleware(request: NextRequest) {
  if (request.nextUrl.pathname.startsWith('/pipeline')) {
    const adminPassword = process.env.KOVALYX_ADMIN_PASSWORD
    if (!adminPassword) {
      // If the password isn't configured, block access entirely rather
      // than falling open.
      return new NextResponse('Pipeline admin not configured.', { status: 503 })
    }

    const authHeader = request.headers.get('authorization')
    if (!authHeader) {
      return new NextResponse('Authentication required.', {
        status: 401,
        headers: { 'WWW-Authenticate': 'Basic realm="Kovalyx Pipeline Admin"' },
      })
    }

    const [scheme, encoded] = authHeader.split(' ')
    if (scheme !== 'Basic' || !encoded) {
      return new NextResponse('Invalid auth format.', { status: 401 })
    }

    const decoded = Buffer.from(encoded, 'base64').toString('utf-8')
    const [, password] = decoded.split(':')

    if (password !== adminPassword) {
      return new NextResponse('Invalid password.', { status: 403 })
    }
  }
  return NextResponse.next()
}

export const config = {
  matcher: ['/pipeline/:path*'],
}
