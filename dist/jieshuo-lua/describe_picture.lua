-- Be My Lens for Jieshuo: describe the current picture.
-- Standalone action. Import or paste this whole file into Jieshuo.
--
-- Change MODE to "focused_item" if you want the answer to focus on the
-- currently focused item instead of describing the whole screen.

local MODE = "describe_screen" -- "describe_screen" or "focused_item"
local DEBUG = false

local ACTION_LABEL = "وصف الصورة باستخدام كن عيني"

if MODE == "focused_item" then
  ACTION_LABEL = "وصف العنصر المحدد باستخدام كن عيني"
end

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

local function toast(message)
  local text = "كن عيني: " .. tostring(message)
  print(text)
  pcall(function()
    Toast.makeText(this, text, Toast.LENGTH_SHORT).show()
  end)
end

local function debug(message)
  if DEBUG then
    toast(message)
  else
    print("كن عيني: " .. tostring(message))
  end
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

local function addDirectoryCandidate(candidates, dir, label)
  if dir ~= nil then
    table.insert(candidates, { dir = dir, label = label })
  end
end

local function outputDirectories()
  local candidates = {}

  local okExternal, externalDir = pcall(function()
    return this.getExternalCacheDir()
  end)
  if okExternal and externalDir ~= nil then
    addDirectoryCandidate(candidates, File(externalDir, "be_my_lens"), "ذاكرة التخزين المؤقت الخارجية")
  end

  local okCache, cacheDir = pcall(function()
    return this.getCacheDir()
  end)
  if okCache and cacheDir ~= nil then
    addDirectoryCandidate(candidates, File(cacheDir, "be_my_lens"), "ذاكرة التخزين المؤقت")
  end

  addDirectoryCandidate(candidates, File("/sdcard/BeMyLens"), "احتياطي /sdcard")
  return candidates
end

local function saveBitmap(bitmap, file)
  local output = nil
  local ok, errorMessage = pcall(function()
    output = FileOutputStream(file)
    local saved = bitmap.compress(Bitmap.CompressFormat.PNG, 90, output)
    output.close()
    output = nil

    if saved == false then
      error("فشل ضغط الصورة")
    end
  end)

  if output ~= nil then
    pcall(function()
      output.close()
    end)
  end

  if not ok then
    return false, errorMessage
  end

  return true, nil
end

local function saveScreenshotAndCreateUri(bitmap)
  local lastError = nil

  for _, candidate in ipairs(outputDirectories()) do
    local ok, result = pcall(function()
      candidate.dir.mkdirs()
      local file = File(candidate.dir, "be_my_lens_" .. MODE .. "_" .. timestamp() .. ".png")
      debug("مسار لقطة الشاشة من " .. candidate.label .. ": " .. tostring(file.getAbsolutePath()))

      local saved, saveError = saveBitmap(bitmap, file)
      if not saved then
        error(tostring(saveError))
      end

      local uri = this.getUriForFile(file)
      if uri == nil then
        error("تعذر إنشاء رابط للصورة")
      end

      return uri
    end)

    if ok and result ~= nil then
      return result, nil
    end

    lastError = tostring(result)
    debug("فشلت محاولة الحفظ في " .. candidate.label .. ": " .. lastError)
  end

  return nil, lastError or "خطأ تخزين غير معروف"
end

local function launchBeMyLens(uri)
  toast("جار الفتح")

  local ok, errorMessage = pcall(function()
    local intent = Intent()
      .setAction(ACTION_DESCRIBE_IMAGE)
      .setComponent(ComponentName(PACKAGE_NAME, ACTIVITY_NAME))
      .setPackage(PACKAGE_NAME)
      .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
      .putExtra("mode", MODE)
      .putExtra("autoSpeak", true)

    intent.setDataAndType(uri, "image/png")
    intent.putExtra(Intent.EXTRA_STREAM, uri)
    intent.putExtra(EXTRA_IMAGE_URI, uri)

    debug("الرابط: " .. tostring(uri))
    this.startActivity(intent)
  end)

  if not ok then
    toast("تعذر فتح التطبيق. " .. tostring(errorMessage))
  end

  return ok
end

local function captureAndLaunch()
  toast(ACTION_LABEL)

  local callbacks = {
    onScreenCaptureDone = function(bitmap)
      local ok, errorMessage = pcall(function()
        local uri, uriError = saveScreenshotAndCreateUri(bitmap)
        if uri == nil then
          toast("تعذر حفظ لقطة الشاشة. " .. tostring(uriError))
          return
        end

        launchBeMyLens(uri)
      end)

      if not ok then
        toast("تعذر تجهيز لقطة الشاشة. " .. tostring(errorMessage))
      end
    end,

    onScreenCaptureFailed = function(errorCode)
      toast("فشل التقاط الشاشة. " .. tostring(errorCode))
    end,

    onScreenCaptureError = function(errorMessage)
      toast("فشل التقاط الشاشة. " .. tostring(errorMessage))
    end,
  }

  local ok, errorMessage = pcall(function()
    this.getScreenShot(node, callbacks)
  end)

  if not ok then
    toast("تعذر التقاط الشاشة. " .. tostring(errorMessage))
  end

  return ok
end

captureAndLaunch()
