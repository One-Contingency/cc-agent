// 第 4 阶段 · 顺序 7
// 写在 lib/api.ts 之后、app/page.tsx 之前。页面外壳，先于具体页面。

// 所有页面共用的外壳。这一步只有语言和正文，导航与登录以后再加。
export default function RootLayout({
  // 当前路由渲染出来的页面，由 Next.js 传进来。
  children,
}: {
  // children 的类型是任意可渲染的 React 节点。
  children: React.ReactNode;
}) {
  // 把外壳返回给 Next.js，由它挂到浏览器文档上。
  return (
    // lang 告诉浏览器这份页面的语言是中文。
    <html lang="zh-CN">
      {/* 第 7 阶段起。各页共用的导航。 */}
      <body>
        {/* 导航。 */}
        <nav>
          {/* 首页。 */}
          <a href="/">首页</a>
          {" "}
          {/* 设置。 */}
          <a href="/settings">设置</a>
          {" "}
          {/* 历史。 */}
          <a href="/history">历史</a>
          {" "}
          {/* 自选。 */}
          <a href="/watchlist">自选</a>
        </nav>
        {/* 当前页面。 */}
        {children}
      </body>
    </html>
  );
}
