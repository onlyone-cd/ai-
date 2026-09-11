import { expect, test, type Page } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("login-form")).toBeVisible();
  await page.getByTestId("login-username").fill("admin");
  await page.getByTestId("login-password").fill("admin123");
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("app-content")).toBeVisible();
  await expect(page.getByTestId("page-candidates")).toBeVisible();
}

test.describe("launch smoke", () => {
  test("login, open resume upload modal, and close it", async ({ page }) => {
    await login(page);

    await page.getByTestId("resume-upload-open").click();
    await expect(page.getByTestId("resume-upload-modal")).toBeVisible();
    await expect(page.getByTestId("resume-upload-submit")).toBeDisabled();

    await page.getByTestId("resume-upload-close").click();
    await expect(page.getByTestId("resume-upload-modal")).toBeHidden();
  });

  test("recruiting job page excludes imported internal jobs", async ({ page }) => {
    await login(page);

    await page.getByTestId("nav-jobs").click();
    await expect(page.getByTestId("page-jobs")).toBeVisible();
    await expect(page.getByTestId("job-list")).not.toContainText("INTERNAL-");

    await page.getByTestId("job-create-toggle").click();
    await expect(page.getByTestId("job-form")).toBeVisible();
  });

  test("agent composer sends with Enter and clears the input", async ({ page }) => {
    await login(page);

    await page.getByTestId("nav-agent").click();
    await expect(page.getByTestId("page-agent")).toBeVisible();

    const input = page.getByTestId("agent-input");
    await input.fill("现在人才库有多少人？");
    await input.press("Enter");
    await expect(input).toHaveValue("");
  });

  test("insight report is responsive and manual refresh bypasses cache", async ({ page }) => {
    await page.setViewportSize({ width: 542, height: 698 });
    await login(page);

    await page.getByRole("combobox").first().selectOption("insight");
    await expect(page.getByTestId("insight-page")).toBeVisible();
    await expect(page.getByTestId("insight-report")).toBeVisible();
    await expect(page.getByTestId("insight-report")).not.toContainText("流失 -");

    const refreshRequest = page.waitForRequest((request) =>
      request.url().includes("/api/insight/report?days=90&refresh=1"),
    );
    await page.getByRole("button", { name: "刷新", exact: true }).click();
    await refreshRequest;

    await page.getByRole("button", { name: "招聘漏斗", exact: true }).click();
    await expect(page.getByRole("heading", { name: "招聘漏斗详情" })).toBeVisible();
    await expect(page.getByText(/候选人-岗位/)).toBeVisible();
  });
});
