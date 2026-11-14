-- Guided Eye (عين الراشد) for Jieshuo: translate the currently selected text.
-- Reads the focused node's text (or content description) and sends it directly
-- to Be My Lens with mode translate_text. No screenshot is captured or shared.
-- Standalone action. Import or paste this whole file into Jieshuo.

local MODE = "translate_text"
local ACTION_LABEL = "ترجمة النص المحدد باستخدام عين الراشد"
local DEBUG = false

require "import"
import "android.content.Intent"
import "android.content.ComponentName"
import "android.widget.Toast"

local PACKAGE_NAME = "io.bemylens.app"
local ACTIVITY_NAME = "io.bemylens.app.JieshuoEntryActivity"
local ACTION_DESCRIBE_IMAGE = "io.bemylens.app.action.DESCRIBE_IMAGE"
local EXTRA_TEXT = "io.bemylens.app.extra.TEXT"

local function toast(message)
  local text = "عين الراشد: " .. tostring(message)
  print(text)
  pcall(function()
    Toast.makeText(this, text, Toast.LENGTH_SHORT).show()
  end)
end

local function debug(message)
  if DEBUG then
    toast(message)
  else
    print("عين الراشد: " .. tostring(message))
  end
end

-- Returns the focused node's text, falling back to its content description.
-- Returns nil when no node exists or neither exposes usable text.
local function selectedText()
  if node == nil then
    debug("لا يوجد عنصر محدد")
    return nil
  end

  local okText, text = pcall(function()
    return node.getText()
  end)
  if okText and text ~= nil and tostring(text) ~= "" then
    debug("نص العنصر: " .. tostring(text))
    return tostring(text)
  end

  local okDesc, desc = pcall(function()
    return node.getContentDescription()
  end)
  if okDesc and desc ~= nil and tostring(desc) ~= "" then
    debug("وصف العنصر: " .. tostring(desc))
    return tostring(desc)
  end

  debug("لا يوجد نص في العنصر المحدد")
  return nil
end

local function launchBeMyLens(text)
  toast("جار الفتح")

  local ok, errorMessage = pcall(function()
    local intent = Intent()
      .setAction(ACTION_DESCRIBE_IMAGE)
      .setComponent(ComponentName(PACKAGE_NAME, ACTIVITY_NAME))
      .setPackage(PACKAGE_NAME)
      .putExtra("mode", MODE)
      .putExtra("autoSpeak", true)
      .putExtra(EXTRA_TEXT, text)

    debug("النص: " .. tostring(text))
    this.startActivity(intent)
  end)

  if not ok then
    toast("تعذر فتح التطبيق. " .. tostring(errorMessage))
  end

  return ok
end

local function translateSelectedText()
  toast(ACTION_LABEL)

  local ok, errorMessage = pcall(function()
    local text = selectedText()
    if text == nil then
      toast("لم يتم العثور على نص محدد")
      return
    end

    launchBeMyLens(text)
  end)

  if not ok then
    toast("تعذر تجهيز النص. " .. tostring(errorMessage))
  end

  return ok
end

translateSelectedText()
