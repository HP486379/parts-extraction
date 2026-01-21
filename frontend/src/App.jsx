import { useCallback, useMemo, useRef, useState } from "react";
import axios from "axios";
import {
  Alert,
  Button,
  Chip,
  Container,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";

/**
 * 目的（A仕様）:
 *  - 検索: PDFアップロード → PART No. 抽出(JSON) → 画面表示
 *  - CSV:  PDFアップロード → parts_list.csv 生成 → ダウンロード
 *
 * 注意:
 *  - L/W/T入力欄は現状未使用（表抽出の動作確認を最優先にするため）
 */

const toFilesFormData = (files) => {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  return formData;
};

function App() {
  const fileInputRef = useRef(null);

  const [files, setFiles] = useState([]);
  const [results, setResults] = useState([]); // { part_number, file_name }
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  // 既存UIを残しているだけ（現状未使用）
  const [lValue, setLValue] = useState("");
  const [wValue, setWValue] = useState("");
  const [tValue, setTValue] = useState("");

  const isSearchDisabled = useMemo(() => files.length === 0 || isLoading, [files, isLoading]);
  const isCsvDisabled = useMemo(() => files.length === 0 || isLoading, [files, isLoading]);

  const handlePickFiles = () => fileInputRef.current?.click();

  const handleFileChange = (e) => {
    const selected = Array.from(e.target.files || []);
    if (!selected.length) return;

    // 同名＋サイズ＋更新時刻で重複排除
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => `${f.name}-${f.size}-${f.lastModified}`));
      const merged = [...prev];
      for (const f of selected) {
        const key = `${f.name}-${f.size}-${f.lastModified}`;
        if (!existing.has(key)) merged.push(f);
      }
      return merged;
    });

    // 同じファイルを再選択できるように
    e.target.value = "";
  };

  const handleClear = () => {
    setFiles([]);
    setResults([]);
    setError("");
  };

  const handleRemoveFile = (idx) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const downloadBlob = (blob, filename) => {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  };

  // A) PART No. 抽出
  const handleSearch = useCallback(async () => {
    if (isSearchDisabled) return;

    setIsLoading(true);
    setError("");
    setResults([]);

    try {
      const response = await axios.post(
        "/api/extract_part_numbers_from_table",
        toFilesFormData(files)
      );

      // backend は
      // [
      //   { file_name, count, part_numbers: [...] },
      //   ...
      // ]
      const rows =
        (response.data || []).flatMap((r) =>
          (r.part_numbers || []).map((p) => ({
            part_number: p,
            file_name: r.file_name,
          }))
        ) || [];

      // 表示を安定させるためソート（PART No → file_name）
      rows.sort((a, b) => {
        const pa = String(a.part_number || "");
        const pb = String(b.part_number || "");
        if (pa !== pb) return pa.localeCompare(pb);
        return String(a.file_name || "").localeCompare(String(b.file_name || ""));
      });

      setResults(rows);
    } catch (err) {
      setError(err?.response?.data?.detail || "PART No. 抽出に失敗しました。");
    } finally {
      setIsLoading(false);
    }
  }, [files, isSearchDisabled]);

  // B) parts_list.csv ダウンロード
  const handleDownloadPartsListCsv = useCallback(async () => {
    if (isCsvDisabled) return;

    setError("");
    try {
      const response = await axios.post(
        "/api/extract_parts_list_csv",
        toFilesFormData(files),
        { responseType: "blob" }
      );

      const blob = new Blob([response.data], { type: "text/csv" });
      downloadBlob(blob, "parts_list.csv");
    } catch (err) {
      setError(err?.response?.data?.detail || "parts_list.csv の生成/ダウンロードに失敗しました。");
    }
  }, [files, isCsvDisabled]);

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Paper elevation={3} sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="h5" fontWeight="bold">
            部品番号抽出ツール
          </Typography>

          {error && <Alert severity="error">{error}</Alert>}

          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              multiple
              style={{ display: "none" }}
              onChange={handleFileChange}
            />
            <Button variant="contained" onClick={handlePickFiles} disabled={isLoading}>
              PDFファイルを選択
            </Button>
            <Button variant="outlined" onClick={handleClear} disabled={isLoading}>
              クリア
            </Button>
            <Typography variant="body2" sx={{ ml: 1 }}>
              選択中: {files.length} 件
            </Typography>
          </Stack>

          {files.length > 0 && (
            <Stack direction="row" spacing={1} flexWrap="wrap">
              {files.map((f, idx) => (
                <Chip
                  key={`${f.name}-${f.size}-${f.lastModified}`}
                  label={f.name}
                  onDelete={() => handleRemoveFile(idx)}
                  sx={{ mb: 1 }}
                />
              ))}
            </Stack>
          )}

          {/* 既存UIを残す（現状未使用） */}
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              label="L値"
              value={lValue}
              onChange={(e) => setLValue(e.target.value)}
              fullWidth
              helperText="※現在この入力は未使用（表ベース抽出の動作確認を優先）"
            />
            <TextField
              label="W値"
              value={wValue}
              onChange={(e) => setWValue(e.target.value)}
              fullWidth
              helperText="※現在この入力は未使用"
            />
            <TextField
              label="T値（厚み）"
              value={tValue}
              onChange={(e) => setTValue(e.target.value)}
              fullWidth
              helperText="※現在この入力は未使用"
            />
          </Stack>

          <Stack direction="row" spacing={2} flexWrap="wrap">
            <Button
              variant="contained"
              onClick={handleSearch}
              disabled={isSearchDisabled}
            >
              {isLoading ? "処理中..." : "検索（PART No.抽出）"}
            </Button>

            <Button
              variant="outlined"
              onClick={handleDownloadPartsListCsv}
              disabled={isCsvDisabled}
            >
              parts_list.csvダウンロード
            </Button>

            {/* 旧「PDF行CSV」は今回は無効化（必要なら復活させます） */}
            <Button variant="outlined" disabled>
              PDF行CSVダウンロード（未使用）
            </Button>
          </Stack>

          <TableContainer sx={{ mt: 1 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: "bold" }}>PART No.</TableCell>
                  <TableCell sx={{ fontWeight: "bold" }}>ファイル名</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {results.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={2} sx={{ color: "text.secondary" }}>
                      {files.length === 0
                        ? "PDFを選択してください。"
                        : "まだ結果がありません。（検索ボタンを押してください）"}
                    </TableCell>
                  </TableRow>
                ) : (
                  results.map((row, i) => (
                    <TableRow key={`${row.part_number}-${row.file_name}-${i}`}>
                      <TableCell>{row.part_number}</TableCell>
                      <TableCell>{row.file_name}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      </Paper>
    </Container>
  );
}

export default App;
