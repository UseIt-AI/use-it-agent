import React from 'react';
import { Loader2, AlertCircle, CheckCircle, Upload, Sparkles, X, ArrowLeft } from 'lucide-react';
import { ExampleTooltipIcon } from './ExampleTooltipIcon';

interface DemoWizardProps {
  step: 1 | 2 | 3;
  description: string;
  onDescriptionChange: (value: string) => void;
  onClose: () => void;
  onNextStep: () => void;
  onPrevStep: () => void;
  onSetStep: (step: 1 | 2 | 3) => void;
  // Recording
  isRecording: boolean;
  isStopping: boolean;
  recordDuration: number;
  recordFilePath: string | undefined;
  recordError: string | null;
  onRecordToggle: () => void;
  // Upload
  uploadStatus: 'idle' | 'presigning' | 'uploading' | 'finalizing' | 'done' | 'error';
  uploadPercent: number;
  uploadError: string | null;
  previewUrl: string | null;
  onStartUpload: () => void;
  // Analyze
  analyzeStatus: 'idle' | 'analyzing' | 'done' | 'error';
  analyzeProgress: number;
  analyzeError: string | null;
  analyzeDescription: string | null;
  // Finish
  onFinish: () => void;
}

export function DemoWizard({
  step,
  description,
  onDescriptionChange,
  onClose,
  onNextStep,
  onPrevStep,
  onSetStep,
  isRecording,
  isStopping,
  recordDuration,
  recordFilePath,
  recordError,
  onRecordToggle,
  uploadStatus,
  uploadPercent,
  uploadError,
  previewUrl,
  onStartUpload,
  analyzeStatus,
  analyzeProgress,
  analyzeError,
  analyzeDescription,
  onFinish,
}: DemoWizardProps) {
  return (
    <div className="w-full h-full bg-[#FAFAFA] flex flex-col items-center justify-center overflow-y-auto font-sans selection:bg-black/5">
      {/* Subtle background pattern */}
      <div 
        className="absolute inset-0 opacity-[0.4] pointer-events-none"
        style={{
          backgroundImage: 'radial-gradient(circle at 1px 1px, rgba(0,0,0,0.03) 1px, transparent 0)',
          backgroundSize: '24px 24px'
        }}
      />

      <div className="w-full max-w-[800px] px-8 py-12 flex flex-col gap-6 animate-in fade-in zoom-in-95 duration-500 relative z-10">
        
        {/* Header */}
        <div className="space-y-2">
          <button
            onClick={onClose}
            className="flex items-center gap-1.5 text-xs text-black/40 hover:text-black transition-colors group mb-4"
          >
            <ArrowLeft className="w-3.5 h-3.5 transition-transform group-hover:-translate-x-0.5" />
            <span className="font-medium">Back</span>
          </button>
          <h1 className="text-xl font-black text-black tracking-tight">Create from Demonstration</h1>
          <p className="text-sm text-black/50 font-medium">
            Record your actions and let AI generate the workflow automatically.
          </p>
        </div>

        {/* Divider */}
        <div className="h-px bg-gradient-to-r from-black/10 via-black/5 to-transparent" />

        {/* Stepper - Updated style */}
        <div className="flex items-center justify-between">
          {/* Step 1 */}
          <div className="flex items-center gap-3">
            <div className={`
              w-8 h-8 flex items-center justify-center text-xs font-bold transition-all
              ${step >= 1 ? 'bg-black text-white' : 'bg-black/[0.06] text-black/40'}
            `}>
              {step > 1 ? (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="square" strokeLinejoin="miter" d="M5 13l4 4L19 7" />
                </svg>
              ) : '1'}
            </div>
            <span className={`text-sm font-semibold transition-colors ${step >= 1 ? 'text-black' : 'text-black/40'}`}>
              Describe
            </span>
          </div>

          {/* Connector */}
          <div className={`flex-1 h-[2px] mx-4 transition-colors ${step >= 2 ? 'bg-black/20' : 'bg-black/[0.06]'}`} />

          {/* Step 2 */}
          <div className="flex items-center gap-3">
            <div className={`
              w-8 h-8 flex items-center justify-center text-xs font-bold transition-all
              ${step >= 2 ? 'bg-black text-white' : 'bg-black/[0.06] text-black/40'}
            `}>
              {step > 2 ? (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="square" strokeLinejoin="miter" d="M5 13l4 4L19 7" />
                </svg>
              ) : '2'}
            </div>
            <span className={`text-sm font-semibold transition-colors ${step >= 2 ? 'text-black' : 'text-black/40'}`}>
              Record
            </span>
          </div>

          {/* Connector */}
          <div className={`flex-1 h-[2px] mx-4 transition-colors ${step >= 3 ? 'bg-black/20' : 'bg-black/[0.06]'}`} />

          {/* Step 3 */}
          <div className="flex items-center gap-3">
            <div className={`
              w-8 h-8 flex items-center justify-center text-xs font-bold transition-all
              ${step >= 3 ? 'bg-black text-white' : 'bg-black/[0.06] text-black/40'}
            `}>
              3
            </div>
            <span className={`text-sm font-semibold transition-colors ${step >= 3 ? 'text-black' : 'text-black/40'}`}>
              Analyze
            </span>
          </div>
        </div>

        {/* Content Card */}
        <div className="bg-white border border-black/[0.08] p-6 overflow-hidden">
          {step === 1 && (
            <Step1Describe
              description={description}
              onDescriptionChange={onDescriptionChange}
              onNext={onNextStep}
            />
          )}

          {step === 2 && (
            <Step2Record
              description={description}
              onDescriptionChange={onDescriptionChange}
              isRecording={isRecording}
              isStopping={isStopping}
              recordDuration={recordDuration}
              recordFilePath={recordFilePath}
              recordError={recordError}
              onRecordToggle={onRecordToggle}
              onSkip={() => onSetStep(3)}
            />
          )}

          {step === 3 && (
            <Step3Analyze
              recordFilePath={recordFilePath}
              uploadStatus={uploadStatus}
              uploadPercent={uploadPercent}
              uploadError={uploadError}
              previewUrl={previewUrl}
              onStartUpload={onStartUpload}
              analyzeStatus={analyzeStatus}
              analyzeProgress={analyzeProgress}
              analyzeError={analyzeError}
              analyzeDescription={analyzeDescription}
              onBack={onPrevStep}
              onFinish={onFinish}
            />
          )}
        </div>

      </div>
    </div>
  );
}

// Step 1: Describe
interface Step1DescribeProps {
  description: string;
  onDescriptionChange: (value: string) => void;
  onNext: () => void;
}

function Step1Describe({ description, onDescriptionChange, onNext }: Step1DescribeProps) {
  return (
    <div className="flex flex-col gap-5">
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-bold text-black/80">Describe Your Workflow</span>
          <ExampleTooltipIcon text="Example: Feishu reimbursement workflow. To achieve the reimbursement form filling and document submission." />
        </div>
        <p className="text-xs text-black/40">Tell us what you want to automate. This helps AI understand your intent.</p>
      </div>
      <textarea
        value={description}
        onChange={(e) => onDescriptionChange(e.target.value)}
        placeholder="e.g., I want to automate the process of filling out expense reports in our company portal..."
        className="w-full h-36 p-4 text-sm bg-[#FAFAFA] border border-black/[0.08] focus:outline-none focus:border-black/20 focus:bg-white transition-all resize-none placeholder:text-black/30"
      />
      <div className="flex justify-end pt-2">
        <button
          onClick={onNext}
          disabled={!description.trim()}
          className="px-6 py-2.5 bg-black text-white text-xs font-bold hover:bg-black/80 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
        >
          Continue
        </button>
      </div>
    </div>
  );
}

// Step 2: Record
interface Step2RecordProps {
  description: string;
  onDescriptionChange: (value: string) => void;
  isRecording: boolean;
  isStopping: boolean;
  recordDuration: number;
  recordFilePath: string | undefined;
  recordError: string | null;
  onRecordToggle: () => void;
  onSkip: () => void;
}

function Step2Record({
  description,
  onDescriptionChange,
  isRecording,
  isStopping,
  recordDuration,
  recordFilePath,
  recordError,
  onRecordToggle,
  onSkip,
}: Step2RecordProps) {
  return (
    <div className="flex flex-col gap-5">
      {/* Editable Description */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-bold text-black/80">Description</span>
          <ExampleTooltipIcon text="Example: Feishu reimbursement workflow. To achieve the reimbursement form filling and document submission." />
        </div>
        <textarea
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          placeholder="Describe the process you are going to record…"
          className="w-full h-24 p-4 text-sm bg-[#FAFAFA] border border-black/[0.08] focus:outline-none focus:border-black/20 focus:bg-white transition-all resize-none placeholder:text-black/30"
        />
      </div>

      {/* Recording Status Card */}
      <div className={`
        p-4 border transition-all
        ${isRecording 
          ? 'bg-red-50/50 border-red-200/60' 
          : isStopping 
            ? 'bg-orange-50/50 border-orange-200/60'
            : 'bg-emerald-50/50 border-emerald-200/60'
        }
      `}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="relative">
              <div
                className={`w-3 h-3 rounded-full ${
                  isStopping ? 'bg-orange-500' : isRecording ? 'bg-red-500' : 'bg-emerald-500'
                }`}
              />
              {(isRecording || isStopping) && (
                <div
                  className={`absolute inset-0 w-3 h-3 rounded-full animate-ping ${
                    isStopping ? 'bg-orange-500/50' : 'bg-red-500/50'
                  }`}
                />
              )}
            </div>
            <div>
              <span className={`text-sm font-semibold ${
                isStopping ? 'text-orange-700' : isRecording ? 'text-red-700' : 'text-emerald-700'
              }`}>
                {isStopping ? 'Stopping…' : isRecording ? `Recording… ${recordDuration}s` : 'Ready to Record'}
              </span>
              <p className="text-xs text-black/40 mt-0.5">
                {isRecording 
                  ? 'Perform your actions on screen. Click Stop when done.' 
                  : 'Click Record to start capturing your screen actions.'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2">
        <button
          onClick={onRecordToggle}
          disabled={isStopping}
          className={`
            flex items-center gap-2 px-6 py-2.5 text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed
            ${isRecording 
              ? 'bg-red-500 text-white hover:bg-red-600' 
              : 'bg-black text-white hover:bg-black/80'
            }
          `}
        >
          <div className="relative w-2.5 h-2.5 flex items-center justify-center">
            <span className={`relative inline-flex w-2 h-2 rounded-full ${isRecording ? 'bg-white' : 'bg-red-500'}`} />
          </div>
          {isRecording ? 'Stop Recording' : 'Start Recording'}
        </button>
        <button
          onClick={onSkip}
          disabled={isRecording || isStopping}
          className="px-6 py-2.5 text-black/40 text-xs font-medium hover:text-black/80 hover:bg-black/5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Skip this step
        </button>
      </div>

      {recordError && (
        <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-100 text-xs text-red-600">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>{recordError}</span>
        </div>
      )}

      {recordFilePath && !isRecording && (
        <div className="text-xs text-black/50 bg-black/[0.02] p-3 border border-black/[0.05]">
          <span className="text-black/40">Saved to:</span>{' '}
          <span className="font-mono text-black/60">{recordFilePath}</span>
        </div>
      )}
    </div>
  );
}

// Step 3: Analyze
interface Step3AnalyzeProps {
  recordFilePath: string | undefined;
  uploadStatus: 'idle' | 'presigning' | 'uploading' | 'finalizing' | 'done' | 'error';
  uploadPercent: number;
  uploadError: string | null;
  previewUrl: string | null;
  onStartUpload: () => void;
  analyzeStatus: 'idle' | 'analyzing' | 'done' | 'error';
  analyzeProgress: number;
  analyzeError: string | null;
  analyzeDescription: string | null;
  onBack: () => void;
  onFinish: () => void;
}

function Step3Analyze({
  recordFilePath,
  uploadStatus,
  uploadPercent,
  uploadError,
  previewUrl,
  onStartUpload,
  analyzeStatus,
  analyzeProgress,
  analyzeError,
  analyzeDescription,
  onBack,
  onFinish,
}: Step3AnalyzeProps) {
  // Determine current state
  const isUploading = uploadStatus === 'presigning' || uploadStatus === 'uploading' || uploadStatus === 'finalizing';
  const isAnalyzing = analyzeStatus === 'analyzing';
  const isDone = analyzeStatus === 'done';
  const hasError = uploadStatus === 'error' || analyzeStatus === 'error';

  return (
    <div className="flex flex-col gap-6 py-6 items-center justify-center text-center">
      {/* Status Icon */}
      <div className={`
        w-14 h-14 flex items-center justify-center transition-all
        ${isDone 
          ? 'bg-gradient-to-br from-orange-400/90 to-amber-600/90 text-white' 
          : hasError
            ? 'bg-red-50 text-red-500'
            : isAnalyzing
              ? 'bg-purple-50 text-purple-600'
              : uploadStatus === 'done'
                ? 'bg-emerald-50 text-emerald-600'
                : 'bg-black/5 text-black/60'
        }
      `}>
        {isDone ? (
          <Sparkles className="w-7 h-7" />
        ) : isAnalyzing ? (
          <Loader2 className="w-7 h-7 animate-spin" />
        ) : hasError ? (
          <AlertCircle className="w-7 h-7" />
        ) : uploadStatus === 'done' ? (
          <CheckCircle className="w-7 h-7" />
        ) : isUploading ? (
          <Loader2 className="w-7 h-7 animate-spin" />
        ) : (
          <Upload className="w-7 h-7" />
        )}
      </div>

      {/* Status Text */}
      <div className="flex flex-col gap-1.5 max-w-md">
        <h3 className="text-lg font-bold text-black/90">
          {!recordFilePath
            ? 'Ready to Create'
            : isDone
              ? 'Analysis Complete!'
              : isAnalyzing
                ? 'Analyzing Your Demo...'
                : uploadStatus === 'done'
                  ? 'Upload Complete'
                  : isUploading
                    ? 'Uploading...'
                    : 'Upload Your Recording'}
        </h3>
        <p className="text-sm text-black/50">
          {!recordFilePath
            ? 'You skipped recording. A workflow will be created based on your description.'
            : isDone
              ? 'AI has analyzed your demonstration and generated the workflow. Ready to create!'
              : isAnalyzing
                ? 'AI is watching your actions and building the workflow logic...'
                : uploadStatus === 'done'
                  ? 'Starting analysis...'
                  : isUploading
                    ? 'Uploading your recording to the cloud...'
                    : 'Upload your recording so AI can analyze and generate the workflow.'}
        </p>
      </div>

      {/* Upload Progress */}
      {recordFilePath && isUploading && (
        <div className="w-full max-w-sm flex flex-col gap-2">
          <div className="w-full h-2 bg-black/[0.06] overflow-hidden">
            <div
              className="h-full bg-black transition-all duration-300 ease-out"
              style={{ width: `${Math.max(5, uploadPercent)}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-black/40 font-medium">
            <span>{uploadStatus === 'presigning' ? 'Preparing...' : uploadStatus === 'finalizing' ? 'Finalizing...' : 'Uploading...'}</span>
            <span>{uploadPercent}%</span>
          </div>
        </div>
      )}

      {/* Analyze Progress */}
      {isAnalyzing && (
        <div className="w-full max-w-sm flex flex-col gap-2">
          <div className="w-full h-2 bg-purple-100 overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-purple-500 to-purple-600 transition-all duration-300 ease-out"
              style={{ width: `${Math.max(5, analyzeProgress)}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-purple-600/70 font-medium">
            <span>{analyzeDescription || 'Analyzing steps...'}</span>
            <span>{analyzeProgress}%</span>
          </div>
        </div>
      )}

      {/* Error Messages */}
      {uploadError && (
        <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-100 text-xs text-red-600 max-w-md text-left">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>Upload error: {uploadError}</span>
        </div>
      )}

      {analyzeError && (
        <div className="p-4 bg-red-50 border border-red-100 max-w-md text-left">
          <div className="flex items-center gap-2 text-sm font-semibold text-red-700 mb-1">
            <AlertCircle className="w-4 h-4" />
            Analysis Error
          </div>
          <p className="text-xs text-red-600 mb-2">{analyzeError}</p>
          <p className="text-xs text-red-500/70">Don't worry - you can still create a basic workflow and edit it manually.</p>
        </div>
      )}

      {/* Preview Link */}
      {previewUrl && !isAnalyzing && !isUploading && (
        <div className="text-xs text-black/50 bg-black/[0.02] px-4 py-2 border border-black/[0.05]">
          Preview:{' '}
          <a className="text-blue-600 hover:underline font-medium" href={previewUrl} target="_blank" rel="noreferrer">
            Open Video
          </a>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3 pt-4">
        <button
          onClick={onBack}
          disabled={isUploading || isAnalyzing}
          className="px-6 py-2.5 border border-black/[0.08] text-black/60 text-xs font-bold hover:bg-black/[0.02] hover:text-black/80 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Back
        </button>

        {!recordFilePath ? (
          <button
            onClick={onFinish}
            className="px-6 py-2.5 bg-black text-white text-xs font-bold hover:bg-black/80 transition-colors"
          >
            Create Workflow
          </button>
        ) : uploadStatus === 'idle' || uploadStatus === 'error' ? (
          <button
            onClick={onStartUpload}
            className="px-6 py-2.5 bg-black text-white text-xs font-bold hover:bg-black/80 transition-colors"
          >
            Upload & Analyze
          </button>
        ) : isDone || analyzeStatus === 'error' ? (
          <button
            onClick={onFinish}
            className={`
              px-6 py-2.5 text-white text-xs font-bold transition-colors
              ${isDone
                ? 'bg-gradient-to-r from-orange-500 to-amber-600 hover:from-orange-600 hover:to-amber-700'
                : 'bg-orange-500 hover:bg-orange-600'
              }
            `}
          >
            {isDone ? 'Create Agent' : 'Create Anyway'}
          </button>
        ) : (
          <button
            disabled
            className="px-6 py-2.5 bg-black/[0.06] text-black/30 text-xs font-bold cursor-not-allowed"
          >
            {isAnalyzing ? 'Analyzing...' : 'Uploading...'}
          </button>
        )}
      </div>
    </div>
  );
}


