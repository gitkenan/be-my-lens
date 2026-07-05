-- Minimal Guided Eye launch prototype for a future Jieshuo .ppk extension.
-- This is not a polished extension. It is a device-testing script.
--
-- Test modes:
--   no_image        verifies explicit Activity launch only
--   describe_screen captures a screenshot and asks Guided Eye to describe it
--   focused_item    captures a screenshot and asks Guided Eye to focus on the item
--
-- Change TEST_MODE before importing/running this script in Jieshuo.

local TEST_MODE = "describe_screen"

require "import"
import "android.content.Intent"
import "android.content.ComponentName"
import "android.graphics.Bitmap"
import "android.widget.Toast"
import "java.io.File"
import "java.io.FileOutputStream"
import "java.lang.System"

local PACKAGE_NAME = "io.bemylens.app"
local ACTIVITY_NAME = "io.bemylens.app.JieshuoEntryActivity"
local ACTION_DESCRIBE_IMAGE = "io.bemylens.app.action.DESCRIBE_IMAGE"
local EXTRA_IMAGE_URI = "io.bemylens.app.extra.IMAGE_URI"

local function notify(message)
  local text = "Guided Eye: " .. tostring(message)
  print(text)
  pcall(function()
    Toast.makeText(this, text, Toast.LENGTH_SHORT).show()
  end)
end

local function timestamp()
  local ok, value = pcall(function()
    return tostring(System.currentTimeMillis())
  end)
  if ok and value ~= nil then
    return value
  end
  return tostring(os.time())
end

local function resolveOutputDirectory()
  local okExternal, externalDir = pcall(function()
    return this.getExternalCacheDir()
  end)
  if okExternal and externalDir ~= nil then
    return externalDir, "external cache"
  end

  local okCache, cacheDir = pcall(function()
    return this.getCacheDir()
  end)
  if okCache and cacheDir ~= nil then
    return cacheDir, "cache"
  end

  -- Prototype fallback only. Prefer a Jieshuo/app cache directory if available.
  return File("/sdcard/"), "temporary /sdcard fallback"
end

local function createScreenshotFile()
  local dir, source = resolveOutputDirectory()
  local name = "be_my_lens_jieshuo_" .. timestamp() .. ".png"
  local file = File(dir, name)
  notify("file path from " .. source .. ": " .. tostring(file.getAbsolutePath()))
  return file
end

local function launchBeMyLens(imageUri, mode, prompt, autoSpeak)
  notify("starting launch, mode=" .. tostring(mode or "describe_screen"))

  local ok, errorMessage = pcall(function()
    local intent = Intent()
      .setAction(ACTION_DESCRIBE_IMAGE)
      .setComponent(ComponentName(PACKAGE_NAME, ACTIVITY_NAME))
      .setPackage(PACKAGE_NAME)
      .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
      .putExtra("mode", mode or "describe_screen")
      .putExtra("autoSpeak", autoSpeak ~= false)

    if prompt ~= nil and prompt ~= "" then
      intent.putExtra("prompt", prompt)
    end

    if imageUri ~= nil then
      notify("URI generated: " .. tostring(imageUri))
      intent.setDataAndType(imageUri, "image/png")
      intent.putExtra(Intent.EXTRA_STREAM, imageUri)
      intent.putExtra(EXTRA_IMAGE_URI, imageUri)
    else
      notify("launching without image URI")
    end

    this.startActivity(intent)
    notify("startActivity called")
  end)

  if not ok then
    notify("launch failed: " .. tostring(errorMessage))
  end

  return ok
end

local function launchNoImageSmokeTest()
  notify("running no-image smoke test")
  return launchBeMyLens(nil, "describe_screen", nil, true)
end

local function captureAndDescribe(mode)
  local resolvedMode = mode or "describe_screen"
  notify("screenshot capture attempted, mode=" .. tostring(resolvedMode))

  local callbacks = {
    onScreenCaptureDone = function(bitmap)
      notify("screenshot capture succeeded")

      local ok, errorMessage = pcall(function()
        local file = createScreenshotFile()
        local output = FileOutputStream(file)
        local saved = bitmap.compress(Bitmap.CompressFormat.PNG, 90, output)
        output.close()

        if saved == false then
          notify("screenshot file save failed")
          return
        end

        notify("screenshot file saved")
        local uri = this.getUriForFile(file)
        launchBeMyLens(uri, resolvedMode, nil, true)
      end)

      if not ok then
        notify("screenshot handling failed: " .. tostring(errorMessage))
      end
    end,

    onScreenCaptureFailed = function(errorCode)
      notify("screenshot capture failed: " .. tostring(errorCode))
    end,

    onScreenCaptureError = function(errorMessage)
      notify("screenshot capture failed: " .. tostring(errorMessage))
    end
  }

  local ok, errorMessage = pcall(function()
    this.getScreenShot(node, callbacks)
  end)

  if not ok then
    notify("screenshot capture call failed: " .. tostring(errorMessage))
  end

  return ok
end

local function runSelectedTest()
  if TEST_MODE == "no_image" then
    return launchNoImageSmokeTest()
  end

  if TEST_MODE == "describe_screen" then
    return captureAndDescribe("describe_screen")
  end

  if TEST_MODE == "focused_item" then
    return captureAndDescribe("focused_item")
  end

  notify("unknown TEST_MODE: " .. tostring(TEST_MODE))
  return false
end

runSelectedTest()
