/*
  env.d.ts — ambient declarations for the bundler (type checking only).
  Defines : CSS imports (`import "./x.css"`): esbuild collects them into app.css.
  Used by : tsc, for every .ts file that imports a stylesheet.
*/
declare module "*.css";
