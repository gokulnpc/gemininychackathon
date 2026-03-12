import test from "node:test";
import assert from "node:assert/strict";

import { applyPuppeteerPatches } from "./render-timeline.mjs";

test("applyPuppeteerPatches patches launch and newPage when both are present", () => {
  const originalLaunch = async () => "launched";
  const originalNewPage = async () => ({
    setDefaultNavigationTimeout: () => {},
    setDefaultTimeout: () => {},
  });

  class MockBrowser {}
  MockBrowser.prototype.newPage = originalNewPage;

  const puppeteerModule = {
    default: { launch: originalLaunch },
    Browser: MockBrowser,
  };

  applyPuppeteerPatches(puppeteerModule);

  assert.notEqual(puppeteerModule.default.launch, originalLaunch, "launch should be replaced");
  assert.notEqual(MockBrowser.prototype.newPage, originalNewPage, "newPage should be replaced");
  assert.equal(typeof puppeteerModule.default.launch, "function");
  assert.equal(typeof MockBrowser.prototype.newPage, "function");
});

test("applyPuppeteerPatches patches only launch when Browser.prototype.newPage is absent", () => {
  const originalLaunch = async () => "launched";

  const puppeteerModule = {
    default: { launch: originalLaunch },
  };

  assert.doesNotThrow(() => applyPuppeteerPatches(puppeteerModule));
  assert.notEqual(puppeteerModule.default.launch, originalLaunch, "launch should be replaced");
});

test("applyPuppeteerPatches throws when puppeteer.launch is unavailable", () => {
  const puppeteerModule = {
    default: {},
  };

  assert.throws(
    () => applyPuppeteerPatches(puppeteerModule),
    (err) => {
      assert.ok(err instanceof Error);
      assert.ok(
        err.message.includes("puppeteer.launch is unavailable"),
        `Unexpected message: ${err.message}`,
      );
      return true;
    },
  );
});

test("applyPuppeteerPatches patches BrowserContext.prototype.newPage and sets page timeouts", async () => {
  const setDefaultNavigationTimeoutCalls = [];
  const setDefaultTimeoutCalls = [];

  const mockPage = {
    setDefaultNavigationTimeout: (ms) => setDefaultNavigationTimeoutCalls.push(ms),
    setDefaultTimeout: (ms) => setDefaultTimeoutCalls.push(ms),
  };

  class MockBrowserContext {}
  MockBrowserContext.prototype.newPage = async () => mockPage;

  const puppeteerModule = {
    default: { launch: async () => {} },
    BrowserContext: MockBrowserContext,
  };

  applyPuppeteerPatches(puppeteerModule);

  assert.notEqual(MockBrowserContext.prototype.newPage.name, "newPage", "newPage should be replaced");

  const returnedPage = await MockBrowserContext.prototype.newPage.call(new MockBrowserContext());
  assert.equal(returnedPage, mockPage);
  assert.deepEqual(setDefaultNavigationTimeoutCalls, [180000]);
  assert.deepEqual(setDefaultTimeoutCalls, [180000]);
});

test("applyPuppeteerPatches patches Page.prototype.goto to inject default timeout", async () => {
  const gotoCalls = [];
  class MockPage {}
  MockPage.prototype.goto = async function (url, options) {
    gotoCalls.push({ url, options });
    return null;
  };

  const puppeteerModule = {
    default: { launch: async () => {} },
    Page: MockPage,
  };

  applyPuppeteerPatches(puppeteerModule);

  assert.notEqual(MockPage.prototype.goto.name, "goto", "goto should be replaced");

  const page = new MockPage();

  // No explicit timeout — should inject 180000
  await page.goto("http://localhost:9100");
  assert.equal(gotoCalls[0].options.timeout, 180000);

  // Explicit timeout — should preserve caller's value
  await page.goto("http://localhost:9100", { timeout: 5000 });
  assert.equal(gotoCalls[1].options.timeout, 5000);
});
